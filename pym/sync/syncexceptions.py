class SyncException(Exception):
	"""base sync exception"""
	def __init__(self,value):
		self.value=value
	def __str__(self):
		return value
