#!/bin/bash

res=0
echo "@@@ Starting puppet-lint check for the modified puppet files @@@"
for file in $(git diff --name-only HEAD^1 | egrep ".pp$"); do
    [[ ! -e $file ]] && continue
    echo "###### Puppetlint for file $file"
    puppet-lint \
        --no-80chars-check \
        --error-level all \
        --fail-on-warnings \
        $file \
    && echo "OK"
    res=$((res+$?))
    echo "################################"
done
if [[ $res -gt 0 ]]; then
    echo "@@@ PUPPETLINT FAILED @@@"
    exit 1
else
    echo "@@@ PUPPETLINT PASSED, CONGRATULATIONS @@@"
fi
