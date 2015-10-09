PYTHON=`which python`
DESTDIR=/
BUILDIR=$(CURDIR)/debian/avocado-virt
PROJECT=avocado
VERSION="0.29.0"
AVOCADO_DIRNAME?=avocado
DIRNAME=$(shell echo $${PWD\#\#*/})

all:
	@echo "make source - Create source package"
	@echo "make install - Install on local system"
	@echo "make build-deb-src - Generate a source debian package"
	@echo "make build-deb-bin - Generate a binary debian package"
	@echo "make build-deb-all - Generate both source and binary debian packages"
	@echo "make build-rpm-all - Generate both source and binary RPMs"
	@echo "make check - Runs static checks in the source code"
	@echo "make clean - Get rid of scratch and byte files"

source:
	$(PYTHON) setup.py sdist $(COMPILE) --dist-dir=SOURCES --prune

install:
	$(PYTHON) setup.py install --root $(DESTDIR) $(COMPILE)

prepare-source:
	# build the source package in the parent directory
	# then rename it to project_version.orig.tar.gz
	dch -D "vivid" -M -v "$(VERSION)" "Automated (make builddeb) build."
	$(PYTHON) setup.py sdist $(COMPILE) --dist-dir=../ --prune
	rename -f 's/$(PROJECT)-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../*

build-deb-src: prepare-source
	# build the source package
	dpkg-buildpackage -S -elookkas@gmail.com -rfakeroot

build-deb-bin: prepare-source
	# build binary package
	dpkg-buildpackage -b -rfakeroot

build-deb-all: prepare-source
	# build both source and binary packages
	dpkg-buildpackage -i -I -rfakeroot

build-rpm-all: source
	rpmbuild --define '_topdir %{getenv:PWD}' \
		 -ba avocado-plugins-vt.spec
check:
	selftests/checkall
clean:
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean || true
	rm -rf build/ MANIFEST BUILD BUILDROOT SPECS RPMS SRPMS SOURCES
	find . -name '*.pyc' -delete

link:
	ln -sf ../../../../$(DIRNAME)/etc/avocado/conf.d/vt.conf ../$(AVOCADO_DIRNAME)/etc/avocado/conf.d/
	ln -sf ../../../../$(DIRNAME)/avocado/core/plugins/vt.py ../$(AVOCADO_DIRNAME)/avocado/core/plugins/
	ln -sf ../../../../$(DIRNAME)/avocado/core/plugins/vt_list.py ../$(AVOCADO_DIRNAME)/avocado/core/plugins/
	ln -sf ../../../../$(DIRNAME)/avocado/core/plugins/vt_bootstrap.py ../$(AVOCADO_DIRNAME)/avocado/core/plugins/
	ln -sf ../$(DIRNAME)/virttest ../$(AVOCADO_DIRNAME)/

unlink:
	test -L ../$(AVOCADO_DIRNAME)/etc/avocado/conf.d/vt.conf && rm -f ../$(AVOCADO_DIRNAME)/etc/avocado/conf.d/vt.conf || true
	test -L ../$(AVOCADO_DIRNAME)/avocado/core/plugins/vt.py && rm -f ../$(AVOCADO_DIRNAME)/avocado/core/plugins/vt.py || true
	test -L ../$(AVOCADO_DIRNAME)/avocado/core/plugins/vt_list.py && rm -f ../$(AVOCADO_DIRNAME)/avocado/core/plugins/vt_list.py || true
	test -L ../$(AVOCADO_DIRNAME)/avocado/core/plugins/vt_bootstrap.py && rm -f ../$(AVOCADO_DIRNAME)/avocado/core/plugins/vt_bootstrap.py || true
	test -L ../$(AVOCADO_DIRNAME)/virttest && rm -f ../$(AVOCADO_DIRNAME)/virttest || true
