# portage.py -- core Portage functionality
# Copyright 1998-2003 Daniel Robbins, Gentoo Technologies, Inc.
# Distributed under the GNU Public License v2
# $Header$

import os,types
import signal
import portage_data
import portage_util

try:
	import resource
	max_fd_limit=resource.getrlimit(RLIMIT_NOFILE)
except:
	# hokay, no resource module.
	max_fd_limit=256

from portage_const import BASH_BINARY,SANDBOX_BINARY,SANDBOX_PIDS_FILE
def spawn_bash(mycommand,env={},debug=False,opt_name=None,**keywords):
	args=[BASH_BINARY]
	if not opt_name:
		opt_name=mycommand.split()[0]
	if not env.has_key("BASH_ENV"):
		env["BASH_ENV"] = "/etc/spork/is/not/valid/profile.env"
	if debug:
		args.append("-x")
	args.append("-c")
	args.append(mycommand)
	return spawn(args,env=env,opt_name=opt_name,**keywords)

def spawn_sandbox(mycommand,uid=None,opt_name=None,**keywords):
	args=[SANDBOX_BINARY]
	if not opt_name:
		opt_name=mycommand.split()[0]
	args.append(mycommand)
	if not uid:
		uid=os.getuid()
	try:
		os.chown(SANDBOX_PIDS_FILE,uid,portage_data.portage_gid)
		os.chmod(SANDBOX_PIDS_FILE,0664)
	except:
		pass
	return spawn(args,uid=uid,**keywords)

# base spawn function
def spawn(mycommand,env={},opt_name=None,fd_pipes=None,returnpid=False,uid=None,gid=None,groups=None,umask=None,logfile=None):
	if type(mycommand)==types.StringType:
		mycommand=mycommand.split()
	if not os.path.exists(mycommand[0]):
		# this sucks. badly.
		return -13
	mypid=[]
	if logfile:
		pr,pw=os.pipe()
		mypid.extend(spawn_bash("PATH=/bin:/usr/bin tee -i -a '%s'" % logfile,returnpid=True,fd_pipes={0:pr,1:1,2:2}))
		retval=os.waitpid(mypid[-1],os.WNOHANG)[1]
		if retval != 0:
			# he's dead jim.
			if (retval & 0xff)==0:
				return (retval >> 8) # exit code
			else:
				return ((retval & 0xff) << 8) # signal
		if not fd_pipes:
			fd_pipes={}
			fd_pipes[0] = 0
		fd_pipes[1]=pw
		fd_pipes[2]=pw
		
	if not opt_name:
		opt_name = mycommand[0]
	myargs=[opt_name]
	myargs.extend(mycommand[1:])
	mypid.append(os.fork())
	if mypid[-1] == 0:
		# this may look ugly, but basically it moves file descriptors around to ensure no 
		# handles that are needed are accidentally closed during the final dup2 calls.
		trg_fd=[]
		if type(fd_pipes)==types.DictType:
			src_fd=[]
			k=fd_pipes.keys()
			k.sort()
			for x in k:
				trg_fd.append(x)
				src_fd.append(fd_pipes[x])
			for x in range(0,len(trg_fd)):
				if trg_fd[x] == src_fd[x]:
					continue
				if trg_fd[x] in src_fd[x+1:]:
					new=os.dup2(trg_fd[x],max(src_fd) + 1)
					os.close(trg_fd[x])
					try:
						while True: 
							src_fd[s.index(trg_fd[x])]=new
					except: pass
			for x in range(0,len(trg_fd)):
				if trg_fd[x] != src_fd[x]:
					os.dup2(src_fd[x], trg_fd[x])
		else:
			trg_fd=[0,1,2]
		for x in range(0,max_fd_limit):
			if x not in trg_fd:
				try: 
					os.close(x)
				except:
					pass
		# note this order must be preserved- can't change gid/groups if you change uid first.
		if gid:
			os.setgid(gid)
		if groups:
			os.setgroups(groups)
		if uid:
			os.setuid(uid)
		if umask:
			os.umask(umask)
		try:
			os.execve(mycommand[0],myargs,env)
		except Exception, e:
			raise str(e)+":\n   "+mycommand+" "+string.join(myargs)
		# If the execve fails, we need to report it, and exit
		# *carefully* --- report error here
		os._exit(1)
		sys.exit(1)
		return # should never get reached

	if logfile:
		os.close(pr)
		os.close(pw)
	
	if returnpid:
		return mypid
	while len(mypid):
		retval=os.waitpid(mypid[-1],0)[1]
		if retval != 0:
			for x in mypid[0:-1]:
				try:
					os.kill(x,signal.SIGTERM)
					if os.waitpid(x,os.WNOHANG)[1] == 0:
						# feisty bugger, still alive.
						os.kill(x,signal.SIGKILL)
					os.waitpid(x,0)
				except OSError, oe:
					if oe.errno not in (10,3):
						raise oe
			
			# at this point we've killed all other kid pids generated via this call.
			# return now.
			
			if (retval & 0xff)==0:
				return (retval >> 8) # return exit code
			else:
				return ((retval & 0xff) << 8) # interrupted by signal
		else:
			mypid.pop(-1)
	return 0

