egrep '^[0-9]+:  \*\*\* emerge' /var/log/emerge.log |
egrep -v 'oneshot|nodeps|emerge .* search ' |
sed 's:^.*\* emerge ::;s:--[^ ]\+ ::;s: :\n:g' |
egrep '^[a-zA-Z=><]' |
egrep -v '^[0-9]|\.ebuild$|\.tbz2$' |
sort -u
