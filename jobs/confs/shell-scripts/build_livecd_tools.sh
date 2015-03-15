#!/bin/bash -xe

echo "Begin building the livecd tools"

pushd livecd-tools-rpm
package_nv=$(rpm -q --qf "%{NAME}-%{VERSION}\n" --specfile livecd-tools.spec |grep livecd)
wget https://fedorahosted.org/releases/l/i/livecd/$package_nv.tar.bz2 -P SOURCES
rpmbuild -bb livecd-tools.spec --define="_topdir `pwd`"
echo "Build finished"
popd

for dir in exported-artifacts; do
    rm -Rf "$dir"
    mkdir -p "$dir"
done

#copy artifacts
cp livecd-tools-rpm/RPMS/x86_64/*.rpm exported-artifacts/


