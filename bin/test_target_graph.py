#!/usr/bin/python

import portage
from portage_dep import *
from portage_syntax import *

vdb = portage.db["/"]["vartree"].dbapi

preferred = []
for cp in vdb.cp_all():
	preferred.append(Atom(cp))

preferred = prepare_prefdict(preferred)

tgraph = StateGraph()

for cp in vdb.cp_all():
	for cpv in vdb.match(cp):
		aux = vdb.aux_get(cpv, ["SLOT","USE","RDEPEND","PDEPEND"])
		slot = aux[0]
		use = aux[1].split()
		rdeps = DependSpec(aux[2] + " " + aux[3], Atom)
		rdeps.resolve_conditions(use)
		pkg = GluePkg(cpv, "installed", slot, use, DependSpec(), rdeps)
		rdeps = transform_virtuals(pkg, rdeps, portage.settings.virtuals)
		rdeps = transform_dependspec(rdeps, preferred)
		pkg = GluePkg(cpv, "installed", slot, use, DependSpec(), rdeps)
		tgraph.add_package(pkg)

#for x in tgraph.pkgrec:
#	print x, tgraph.pkgrec[x]

print
print tgraph.pkgrec
print
print tgraph.unmatched_atoms
print
print tgraph.unmatched_preferentials
print
print tgraph.preferential_atoms
print
print tgraph.reverse_preferentials
