# portage.py -- core Portage functionality
# Copyright 1998-2003 Daniel Robbins, Gentoo Technologies, Inc.
# Distributed under the GNU Public License v2
# $Header$

import os
import portage_data
import portage_util
from portage_const import BASH_BINARY,SANDBOX_BINARY,SANDBOX_PIDS_FILE

# XXX fd_pipes should be a way for a process to communicate back.
# XXX This would be to replace getstatusoutput completely.
# XXX Issue: cannot block execution. Deadlock condition.
def spawn(mystring,debug=0,free=0,droppriv=0,fd_pipes=None,returndpid=False):
	"""spawn a subprocess with optional sandbox protection, 
	depending on whether sandbox is enabled.  The "free" argument,
	when set to 1, will disable sandboxing.  This allows us to 
	spawn processes that are supposed to modify files outside of the
	sandbox.  We can't use os.system anymore because it messes up
	signal handling.  Using spawn allows our Portage signal handler
	to work."""

	mycommand = BASH_BINARY
	if debug:
		myargs=["bash","-x","-c",mystring]
	else:
		myargs=["bash","-c",mystring]

	mypid=os.fork()
	if mypid==0:
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
		try:
			import resource
			max_limit=resource.getrlimit(RLIMIT_NOFILE)
		except:
			# hokay, no resource module.
			max_limit=256
		for x in range(0,max_limit):
			if x not in trg_fd:
				try: 
					os.close(x)
				except:
					pass
		if droppriv:
			if portage_data.portage_gid and portage_data.portage_uid:
				#drop root privileges, become the 'portage' user
				os.setgid(portage_data.portage_gid)
				os.setgroups([portage_data.portage_gid])
				os.setuid(portage_data.portage_uid)
				os.umask(002)
				try:
					os.chown(SANDBOX_PIDS_FILE,uid,portage_data.portage_gid)
					os.chmod(SANDBOX_PIDS_FILE,0664)
				except:
					pass
			else:
				portage_util.writemsg("portage: Unable to drop root for "+str(mystring)+"\n")
		
		try:
			os.execv(mycommand,myargs)
		except Exception, e:
			raise str(e)+":\n   "+mycommand+" "+string.join(myargs)
		# If the execve fails, we need to report it, and exit
		# *carefully* --- report error here
		os._exit(1)
		sys.exit(1)
		return # should never get reached
	if returnpid:
		return [mypid]
	retval=os.waitpid(mypid,0)[1]
	if (retval & 0xff)==0:
		return (retval >> 8) # return exit code
	else:
		return ((retval & 0xff) << 8) # interrupted by signal
