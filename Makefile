ifndef PYTHON
PYTHON=$(shell which python3 2>/dev/null || which python2 2>/dev/null || which python 2>/dev/null)
endif
VERSION=$(shell $(PYTHON) setup.py --version 2>/dev/null)
PYTHON_DEVELOP_ARGS=$(shell if ($(PYTHON) setup.py develop --help 2>/dev/null | grep -q '\-\-user'); then echo "--user"; else echo ""; fi)
DESTDIR=/
AVOCADO_DIRNAME?=avocado

RELEASE_COMMIT=$(shell git log --abbrev=8 --pretty=format:'%H' -n 1 $(VERSION))
RELEASE_SHORT_COMMIT=$(shell git log --abbrev=8 --pretty=format:'%h' -n 1 $(VERSION))

COMMIT=$(shell git log --abbrev=8 --pretty=format:'%H' -n 1)
COMMIT_DATE=$(shell git log --pretty='format:%cd' --date='format:%Y%m%d' -n 1)
SHORT_COMMIT=$(shell git log --abbrev=8 --pretty=format:'%h' -n 1)
MOCK_CONFIG=default
ARCHIVE_BASE_NAME=avocado-vt
RPM_BASE_NAME=avocado-plugins-vt

include Makefile.include

all:
	@echo
	@echo "Development related targets:"
	@echo "check:    Runs tree static check, unittests and fast functional tests"
	@echo "develop:  Runs 'python setup.py --develop' on this tree alone"
	@echo "link:     Runs 'python setup.py --develop' in all subprojects and links the needed resources"
	@echo "clean:    Get rid of scratch, byte files and removes the links to other subprojects"
	@echo "unlink:   Disables egg links and unlinks needed resources"
	@echo
	@echo "Platform independent distribution/installtion related targets:"
	@echo "source:   Create source package"
	@echo "install:  Install on local system"
	@echo
	@echo "RPM related targets:"
	@echo "srpm:  Generate a source RPM package (.srpm)"
	@echo "rpm:   Generate binary RPMs"
	@echo
	@echo "Release related targets:"
	@echo "source-release:  Create source package for the latest tagged release"
	@echo "srpm-release:    Generate a source RPM package (.srpm) for the latest tagged release"
	@echo "rpm-release:     Generate binary RPMs for the latest tagged release"
	@echo

requirements: pip
	- $(PYTHON) -m pip install "pip>=6.0.1"
	- $(PYTHON) -m pip install -r requirements.txt

check:
	inspekt checkall --disable-lint W,R,C,E1002,E1101,E1103,E1120,F0401,I0011,E1003 --no-license-check

clean:
	$(PYTHON) setup.py clean
	rm -rf build/ MANIFEST BUILD BUILDROOT SPECS RPMS SRPMS SOURCES
	find . -name '*.pyc' -delete

develop:
	$(PYTHON) setup.py develop $(PYTHON_DEVELOP_ARGS)

link: develop
	for CONF in etc/avocado/conf.d/*; do\
		[ -d "../$(AVOCADO_DIRNAME)/avocado/etc/avocado/conf.d" ] && ln -srf $(CURDIR)/$$CONF ../$(AVOCADO_DIRNAME)/avocado/$$CONF || true;\
		[ -d "../$(AVOCADO_DIRNAME)/etc/avocado/conf.d" ] && ln -srf $(CURDIR)/$$CONF ../$(AVOCADO_DIRNAME)/$$CONF || true;\
	done

unlink:
	$(PYTHON) setup.py develop --uninstall $(PYTHON_DEVELOP_ARGS)
	for CONF in etc/avocado/conf.d/*; do\
		[ -L ../$(AVOCADO_DIRNAME)/avocado/$$CONF ] && rm -f ../$(AVOCADO_DIRNAME)/avocado/$$CONF || true;\
		[ -L ../$(AVOCADO_DIRNAME)/$$CONF ] && rm -f ../$(AVOCADO_DIRNAME)/$$CONF || true;\
	done
