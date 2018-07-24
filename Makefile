PYTHON=$(shell which python)
PYTHON_DEVELOP_ARGS=$(shell if ($(PYTHON) setup.py develop --help 2>/dev/null | grep -q '\-\-user'); then echo "--user"; else echo ""; fi)
DESTDIR=/
BUILDIR=$(CURDIR)/debian/avocado-vt
PROJECT=avocado
VERSION=$(shell cat $(CURDIR)/VERSION)
AVOCADO_DIRNAME?=avocado

RELEASE_COMMIT=$(shell git log --abbrev=8 --pretty=format:'%H' -n 1 $(VERSION))
RELEASE_SHORT_COMMIT=$(shell git log --abbrev=8 --pretty=format:'%h' -n 1 $(VERSION))

COMMIT=$(shell git log --abbrev=8 --pretty=format:'%H' -n 1)
SHORT_COMMIT=$(shell git log --abbrev=8 --pretty=format:'%h' -n 1)

all:
	@echo
	@echo "Development related targets:"
	@echo "check:  Runs tree static check, unittests and functional tests"
	@echo "clean:  Get rid of scratch and byte files"
	@echo "link:  Enables egg links and links needed resources"
	@echo "unlink:  Disables egg links and unlinks needed resources"
	@echo
	@echo "Platform independent distribution/installtion related targets:"
	@echo "source:   Create source package"
	@echo "install:  Install on local system"
	@echo
	@echo "RPM related targets:"
	@echo "srpm:  Generate a source RPM package (.srpm)"
	@echo "rpm:   Generate binary RPMs"
	@echo
	@echo "Debian related targets:"
	@echo "deb:      Generate both source and binary debian packages"
	@echo "deb-src:  Generate a source debian package"
	@echo "deb-bin:  Generate a binary debian package"
	@echo
	@echo "Release related targets:"
	@echo "source-release:  Create source package for the latest tagged release"
	@echo "srpm-release:    Generate a source RPM package (.srpm) for the latest tagged release"
	@echo "rpm-release:     Generate binary RPMs for the latest tagged release"
	@echo


source: clean
	if test ! -d SOURCES; then mkdir SOURCES; fi
	git archive --prefix="avocado-vt-$(COMMIT)/" -o "SOURCES/avocado-vt-$(VERSION)-$(SHORT_COMMIT).tar.gz" HEAD

source-release: clean
	if test ! -d SOURCES; then mkdir SOURCES; fi
	git archive --prefix="avocado-plugins-vt-$(RELEASE_COMMIT)/" -o "SOURCES/avocado-plugins-vt-$(VERSION)-$(RELEASE_SHORT_COMMIT).tar.gz" $(VERSION)

install:
	$(PYTHON) setup.py install --root $(DESTDIR) $(COMPILE)

prepare-source:
	# build the source package in the parent directory
	# then rename it to project_version.orig.tar.gz
	dch -D "vivid" -M -v "$(VERSION)" "Automated (make builddeb) build."
	$(PYTHON) setup.py sdist $(COMPILE) --dist-dir=../ --prune
	rename -f 's/$(PROJECT)-(.*)\.tar\.gz/$(PROJECT)_$$1\.orig\.tar\.gz/' ../*

deb-src: prepare-source
	# build the source package
	dpkg-buildpackage -S -elookkas@gmail.com -rfakeroot

deb-bin: prepare-source
	# build binary package
	dpkg-buildpackage -b -rfakeroot

deb: prepare-source
	# build both source and binary packages
	dpkg-buildpackage -i -I -rfakeroot

srpm: source
	if test ! -d BUILD/SRPM; then mkdir -p BUILD/SRPM; fi
	mock --old-chroot --resultdir BUILD/SRPM -D "commit $(COMMIT)" --buildsrpm --spec avocado-plugins-vt.spec --sources SOURCES

rpm: srpm
	if test ! -d BUILD/RPM; then mkdir -p BUILD/RPM; fi
	mock --old-chroot --resultdir BUILD/RPM -D "commit $(COMMIT)" --rebuild BUILD/SRPM/avocado-plugins-vt-$(VERSION)-*.src.rpm

srpm-release: source-release
	if test ! -d BUILD/SRPM; then mkdir -p BUILD/SRPM; fi
	mock --old-chroot --resultdir BUILD/SRPM -D "commit $(RELEASE_COMMIT)" --buildsrpm --spec avocado-plugins-vt.spec --sources SOURCES

rpm-release: srpm-release
	if test ! -d BUILD/RPM; then mkdir -p BUILD/RPM; fi
	mock --old-chroot --resultdir BUILD/RPM -D "commit $(RELEASE_COMMIT)" --rebuild BUILD/SRPM/avocado-plugins-vt-$(VERSION)-*.src.rpm

requirements:
	- pip install "pip>=6.0.1"
	- pip install -r requirements.txt

check:
	inspekt checkall --disable-lint W,R,C,E1002,E1101,E1103,E1120,F0401,I0011,E1003 --no-license-check

clean:
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean || true
	rm -rf build/ MANIFEST BUILD BUILDROOT SPECS RPMS SRPMS SOURCES
	find . -name '*.pyc' -delete

link:
	for CONF in etc/avocado/conf.d/*; do\
		[ -d "../$(AVOCADO_DIRNAME)/avocado/etc/avocado/conf.d" ] && ln -srf $(CURDIR)/$$CONF ../$(AVOCADO_DIRNAME)/avocado/$$CONF || true;\
		[ -d "../$(AVOCADO_DIRNAME)/etc/avocado/conf.d" ] && ln -srf $(CURDIR)/$$CONF ../$(AVOCADO_DIRNAME)/$$CONF || true;\
	done
	$(PYTHON) setup.py develop  $(PYTHON_DEVELOP_ARGS)

unlink:
	$(PYTHON) setup.py develop --uninstall $(PYTHON_DEVELOP_ARGS)
	for CONF in etc/avocado/conf.d/*; do\
		[ -L ../$(AVOCADO_DIRNAME)/avocado/$$CONF ] && rm -f ../$(AVOCADO_DIRNAME)/avocado/$$CONF || true;\
		[ -L ../$(AVOCADO_DIRNAME)/$$CONF ] && rm -f ../$(AVOCADO_DIRNAME)/$$CONF || true;\
	done
