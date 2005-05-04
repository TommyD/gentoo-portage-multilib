#!/usr/bin/python

import portage
from portage_dep import *
from portage_syntax import *

vdb = portage.db["/"]["vartree"].dbapi

preferred = []
for cp in vdb.cp_all():
	preferred.append(Atom(cp))

preferred = prepare_prefdict(preferred)

tgraph = TargetGraph()

for cp in vdb.cp_all():
	for cpv in vdb.match(cp):
		aux = vdb.aux_get(cpv, ["SLOT","USE","RDEPEND","PDEPEND"])
		slot = aux[0]
		use = aux[1].split()
		rdeps = DependSpec(aux[2] + " " + aux[3], Atom)
		rdeps.resolve_conditions(use)
		transform_dependspec(rdeps, preferred)
		y = str(rdeps)
		pkg = GluePkg(cpv, "installed", slot, use, DependSpec(), rdeps)
		tgraph.add_package(pkg)

for x in tgraph.unmatched_atoms.keys():
	if portage.settings.virtuals.has_key(x):
		cpv = x+"-1.0"
		slot = "0"
		use = []
		rdeps = DependSpec("|| ( "+" ".join(portage.settings.virtuals[x])+" )", Atom)
		pkg = GluePkg(cpv, "virtual", slot, use, DependSpec(), rdeps)
		tgraph.add_package(pkg)

for x in tgraph.pkgrec:
	if tgraph.pkgrec[x][1]:
		print x, tgraph.pkgrec[x]

print tgraph.unmatched_atoms
