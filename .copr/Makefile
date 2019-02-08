pkg_install := $(shell dnf -y install git rpm-build)
commit := $(shell git log --pretty=format:'%H' -n 1)
commit_date := $(shell git log --pretty='format:%cd' --date='format:%Y%m%d' -n 1)
short_commit := $(shell git log --pretty=format:'%h' -n 1)

srpm:
	if test ! -d SOURCES; then mkdir SOURCES; fi
	if test ! -d SPEC; then mkdir SPEC; fi
	git archive --prefix="avocado-vt-$(commit)/" -o "SOURCES/avocado-vt-$(short_commit).tar.gz" HEAD
	cp avocado-plugins-vt.spec SPEC
	sed -i -e 's/\%global rel_build .*/\%global rel_build 0/' SPEC/avocado-plugins-vt.spec
	sed -i -e 's/\%global commit .*/\%global commit $(commit)/' SPEC/avocado-plugins-vt.spec
	sed -i -e 's/\%global commit_date .*/\%global commit_date $(commit_date)/' SPEC/avocado-plugins-vt.spec
	rpmbuild -D '_topdir .' -bs SPEC/avocado-plugins-vt.spec
	mv SRPMS/*.src.rpm $(outdir)
