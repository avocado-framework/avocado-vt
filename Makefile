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

include Makefile.include

requirements: pip
	- $(PYTHON) -m pip install -r requirements.txt

check:
	./avocado-static-checks/check-style
	./avocado-static-checks/check-import-order
	inspekt lint --disable W,R,C,E0203,E0601,E1002,E1101,E1102,E1103,E1120,F0401,I0011,E1003,W605,I1101 --exclude avocado-libs,scripts/github
	pylint --errors-only --disable=all --enable=spelling --spelling-dict=en_US --spelling-private-dict-file=spell.ignore *

clean:
	$(PYTHON) setup.py clean

develop:
	$(PYTHON) setup.py develop $(PYTHON_DEVELOP_ARGS)

link: develop

unlink:
	$(PYTHON) setup.py develop --uninstall $(PYTHON_DEVELOP_ARGS)
	# For compatibility reasons remove old symlinks
	for NAME in $$(ls -1 avocado_vt/conf.d); do\
		CONF="etc/avocado/conf.d/$$NAME";\
		[ -L ../$(AVOCADO_DIRNAME)/avocado/$$CONF ] && rm -f ../$(AVOCADO_DIRNAME)/avocado/$$CONF || true;\
		[ -L ../$(AVOCADO_DIRNAME)/$$CONF ] && rm -f ../$(AVOCADO_DIRNAME)/$$CONF || true;\
	done

pypi: clean
	if test ! -d PYPI_UPLOAD; then mkdir PYPI_UPLOAD; fi
	$(PYTHON) setup.py bdist_wheel -d PYPI_UPLOAD
	$(PYTHON) setup.py sdist -d PYPI_UPLOAD
	@echo
	@echo "Please use the files on PYPI_UPLOAD dir to upload a new version to PyPI"
	@echo "The URL to do that may be a bit tricky to find, so here it is:"
	@echo " https://pypi.python.org/pypi?%3Aaction=submit_form"
	@echo
	@echo "Alternatively, you can also run a command like: "
	@echo " twine upload -u <PYPI_USERNAME> PYPI_UPLOAD/*.{tar.gz,whl}"
	@echo
