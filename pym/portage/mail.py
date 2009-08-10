# portage.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage.exception, socket, smtplib, os, sys, time
from email.MIMEText import MIMEText as TextMessage
from email.MIMEMultipart import MIMEMultipart as MultipartMessage
from email.MIMEBase import MIMEBase as BaseMessage
from email.header import Header

def create_message(sender, recipient, subject, body, attachments=None):

	if sys.hexversion < 0x3000000:
		if isinstance(sender, unicode):
			sender = sender.encode('utf_8', 'replace')
		if isinstance(recipient, unicode):
			recipient = recipient.encode('utf_8', 'replace')
		if isinstance(subject, unicode):
			subject = subject.encode('utf_8', 'replace')
		if isinstance(body, unicode):
			body = body.encode('utf_8', 'replace')

	if attachments == None:
		mymessage = TextMessage(body)
	else:
		mymessage = MultipartMessage()
		mymessage.attach(TextMessage(body))
		for x in attachments:
			if isinstance(x, BaseMessage):
				mymessage.attach(x)
			elif isinstance(x, basestring):
				if sys.hexversion < 0x3000000 and isinstance(x, unicode):
					x = x.encode('utf_8', 'replace')
				mymessage.attach(TextMessage(x))
			else:
				raise portage.exception.PortageException("Can't handle type of attachment: %s" % type(x))

	mymessage.set_unixfrom(sender)
	mymessage["To"] = recipient
	mymessage["From"] = sender
	# Use Header as a workaround so that long subject lines are wrapped
	# correctly by <=python-2.6 (gentoo bug #263370, python issue #1974).
	mymessage["Subject"] = Header(subject)
	mymessage["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S %z")
	
	return mymessage

def send_mail(mysettings, message):
	mymailhost = "localhost"
	mymailport = 25
	mymailuser = ""
	mymailpasswd = ""
	myrecipient = "root@localhost"
	
	# Syntax for PORTAGE_ELOG_MAILURI (if defined):
	# adress [[user:passwd@]mailserver[:port]]
	# where adress:     recipient adress
	#       user:       username for smtp auth (defaults to none)
	#       passwd:     password for smtp auth (defaults to none)
	#       mailserver: smtp server that should be used to deliver the mail (defaults to localhost)
	#					alternatively this can also be the absolute path to a sendmail binary if you don't want to use smtp
	#       port:       port to use on the given smtp server (defaults to 25, values > 100000 indicate that starttls should be used on (port-100000))
	if " " in mysettings["PORTAGE_ELOG_MAILURI"]:
		myrecipient, mymailuri = mysettings["PORTAGE_ELOG_MAILURI"].split()
		if "@" in mymailuri:
			myauthdata, myconndata = mymailuri.rsplit("@", 1)
			try:
				mymailuser,mymailpasswd = myauthdata.split(":")
			except ValueError:
				print "!!! invalid SMTP AUTH configuration, trying unauthenticated ..."
		else:
			myconndata = mymailuri
		if ":" in myconndata:
			mymailhost,mymailport = myconndata.split(":")
		else:
			mymailhost = myconndata
	else:
		myrecipient = mysettings["PORTAGE_ELOG_MAILURI"]
	
	myfrom = message.get("From")

	if sys.hexversion < 0x3000000:
		if isinstance(myrecipient, unicode):
			myrecipient = myrecipient.encode('utf_8', 'replace')
		if isinstance(mymailhost, unicode):
			mymailhost = mymailhost.encode('utf_8', 'replace')
		if isinstance(mymailport, unicode):
			mymailport = mymailport.encode('utf_8', 'replace')
		if isinstance(myfrom, unicode):
			myfrom = myfrom.encode('utf_8', 'replace')
		if isinstance(mymailuser, unicode):
			mymailuser = mymailuser.encode('utf_8', 'replace')
		if isinstance(mymailpasswd, unicode):
			mymailpasswd = mymailpasswd.encode('utf_8', 'replace')

	# user wants to use a sendmail binary instead of smtp
	if mymailhost[0] == os.sep and os.path.exists(mymailhost):
		fd = os.popen(mymailhost+" -f "+myfrom+" "+myrecipient, "w")
		fd.write(message.as_string())
		if fd.close() != None:
			sys.stderr.write("!!! %s returned with a non-zero exit code. This generally indicates an error.\n" % mymailhost)
	else:
		try:
			if int(mymailport) > 100000:
				myconn = smtplib.SMTP(mymailhost, int(mymailport) - 100000)
				myconn.ehlo()
				if not myconn.has_extn("STARTTLS"):
					raise portage.exception.PortageException("!!! TLS support requested for logmail but not suported by server")
				myconn.starttls()
				myconn.ehlo()
			else:
				myconn = smtplib.SMTP(mymailhost, mymailport)
			if mymailuser != "" and mymailpasswd != "":
				myconn.login(mymailuser, mymailpasswd)
			myconn.sendmail(myfrom, myrecipient, message.as_string())
			myconn.quit()
		except smtplib.SMTPException, e:
			raise portage.exception.PortageException("!!! An error occured while trying to send logmail:\n"+str(e))
		except socket.error, e:
			raise portage.exception.PortageException("!!! A network error occured while trying to send logmail:\n"+str(e)+"\nSure you configured PORTAGE_ELOG_MAILURI correctly?")
	return
	
