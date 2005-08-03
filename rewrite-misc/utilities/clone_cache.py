#!/usr/bin/python
import portage.config, sys, time

if __name__ == "__main__":
	verbose = 0
	if len(sys.argv) not in (3,4):
		print "I need 2 args, cache label to read from, cache label to write to, with -v optional for verbose"
	elif len(sys.argv) == 4:
		verbose = 1
	c=portage.config.load_config()
	try:	cache1 = c.cache[sys.argv[1]]
	except KeyError:
		print "read cache label '%s' isn't defined." % sys.argv[1]
		sys.exit(1)
	try:	cache2 = c.cache[sys.argv[2]]
	except KeyError:
		print "write cache label '%s' isn't defined." % sys.argv[2]
		sys.exit(1)

	if cache2.readonly:
		print "can't update cache label '%s', it's marked readonly." % sys.argv[2]
		sys.exit(2)
	if not cache2.autocommits:
		cache2.sync_rate = 1000
	if verbose:	print "grabbing cache2's existing keys"
	valid = {}
	start = time.time()
	if verbose:
		for k,v in cache1.iteritems():
			print "updating %s" % k
			cache2[k] = v
			valid[k] = True
	else:
		for k,v in cache1.iteritems():
			cache2[k] = v
			valid[k] = True

	for x in cache2.iterkeys():
		if not x in valid:
			if verbose:	print "deleting %s" % x
			del cache2[x]
	
	if verbose:
		print "took %i seconds" % int(time.time() - start)
