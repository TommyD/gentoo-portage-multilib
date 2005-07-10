# Author(s): Lifted from python cookbook, Scott David Daniels, Ben Wolfson, Nick Perkins, Alex Martelli for curry routine.
# License: GPL2

def curry(*args, **kargs):
	def callit(*moreargs, **morekargs):
		kw = kargs.copy()
		kw.update(morekargs)
		return args[0](*(args[1:]+moreargs), **kw)
	return callit
