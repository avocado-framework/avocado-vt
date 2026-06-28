# Copyright 2013-2020 Intranet AG and contributors
#
# avocado-i2n is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# avocado-i2n is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with avocado-i2n.  If not, see <http://www.gnu.org/licenses/>.

"""
Module for handling all Cartesian config parsing and making it reusable and maximally performant.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

import os
import copy
import collections
import logging

from virttest import cartesian_config
from virttest.utils_params import Params
from avocado.core.settings import settings

log = logging.getLogger("avocado.job." + __name__)


class EmptyCartesianProduct(Exception):
    """Empty Cartesian product of variants."""

    def __init__(self, message: str) -> None:
        """
        Initialize an empty Cartesian product exception.

        :param message: additional message about the exception
        """
        message = "Empty Cartesian product of parameters!\n" + message
        message = (
            "Check for self-excluding variants in your current configuration:\n"
            + message
        )
        super(EmptyCartesianProduct, self).__init__(message)


###################################################################
# preprocessing
###################################################################


_devel_tp_folder = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "tp_folder")
)
settings.register_option(
    section="i2n.common",
    key="suite_path",
    key_type=str,
    default=_devel_tp_folder,
    help_msg="Path to the test suite containing Cartesian variants and test scripts.",
)


def custom_configs_dir() -> str:
    """Get custom directory for all config files."""
    suite_path = settings.as_dict().get("i2n.common.suite_path")
    return os.path.join(suite_path, "configs")


def tests_ovrwrt_file() -> str:
    """Get overwrite file for all tests (nodes)."""
    ovrwrt_file = os.path.join(os.environ["HOME"], "avocado_overwrite_tests.cfg")
    if not os.path.exists(ovrwrt_file):
        logging.warning(
            "Generating a file to use for overwriting the original test parameters"
        )
        with open(ovrwrt_file, "w") as handle:
            handle.write(
                "# Use this config to override with test nodes configuration\n"
                "include "
                + os.path.join(custom_configs_dir(), "sets-overwrite.cfg")
                + "\n"
            )
    return ovrwrt_file


def vms_ovrwrt_file() -> str:
    """Get overwrite file for all vms (a category of objects)."""
    ovrwrt_file = os.path.join(os.environ["HOME"], "avocado_overwrite_vms.cfg")
    if not os.path.exists(ovrwrt_file):
        logging.warning(
            "Generating a file to use for overwriting the original vm parameters"
        )
        with open(ovrwrt_file, "w") as handle:
            handle.write(
                "# Use this config to override with test objects configuration\n"
                "include "
                + os.path.join(custom_configs_dir(), "objects-overwrite.cfg")
                + "\n"
            )
    return ovrwrt_file


def ovrwrt_file(category: str) -> str:
    """Get overwrite file for all objects."""
    ovrwrt_file = os.path.join(os.environ["HOME"], f"avocado_overwrite_{category}.cfg")
    if not os.path.exists(ovrwrt_file):
        logging.warning(
            f"Generating a file to use for overwriting the original {category} parameters"
        )
        with open(ovrwrt_file, "w") as handle:
            handle.write(
                "# Use this config to override with test objects configuration\n"
                "include "
                + os.path.join(custom_configs_dir(), f"{category}-overwrite.cfg")
                + "\n"
            )
    return ovrwrt_file


###################################################################
# main parameter parsing methods
###################################################################


class ParsedContent:
    """Class for parsed content of a general type."""

    def __init__(self, content: str) -> None:
        """Initialize the parsed content."""
        self.content = content

    def reportable_form(self) -> str:
        """
        Get parsed content representation used in reports of parsing steps.

        :returns: resulting report-compatible string
        :raises: :py:class:`NotImlementedError` as this is an abstract method
        """
        raise NotImlementedError(
            "Parsed content is an abstract class with no parsalbe form"
        )

    def parsable_form(self) -> str:
        """
        Convert parameter content into parsable string.

        :returns: resulting parsable string
        :raises: :py:class:`NotImlementedError` as this is an abstract method
        """
        raise NotImlementedError(
            "Parsed content is an abstract class with no parsalbe form"
        )


class ParsedFile(ParsedContent):
    """Class for parsed content of file type."""

    def __init__(self, content: str) -> None:
        """Initialize the parsed content."""
        super().__init__(content)
        self.filename = content

    def reportable_form(self) -> str:
        """
        Get parsed file representation used in reports of parsing steps.

        Arguments are identical to the ones of the parent class.
        """
        return "\tParsed file:\n\t\t%s\n" % self.content

    def parsable_form(self) -> str:
        """
        Convert parameter file name into parsable string.

        :returns: resulting parsable string
        """
        return "include %s\n" % self.content


class ParsedStr(ParsedContent):
    """Class for parsed content of string type."""

    def reportable_form(self) -> str:
        """
        Get parsed string representation used in reports of parsing steps.

        Arguments are identical to the ones of the parent class.
        """
        return "\tParsed string:\n\t\t%s\n" % self.content.rstrip("\n").replace(
            "\n", "\n\t\t"
        )

    def parsable_form(self) -> str:
        """
        Convert parameter string into parsable string.

        :returns: resulting parsable string

        This is equivalent to the string since the string
        is parsable by definition.
        """
        return self.content


class ParsedDict(ParsedContent):
    """Class for parsed content of dictionary type."""

    def reportable_form(self) -> str:
        """
        Get parsed dictionary representation used in reports of parsing steps.

        Arguments are identical to the ones of the parent class.
        """
        return "\tParsed dictionary:\n\t\t%s\n" % self.parsable_form().rstrip(
            "\n"
        ).replace("\n", "\n\t\t")

    def parsable_form(self) -> str:
        """
        Convert parameter dictionary into parsable string.

        :returns: resulting parsable string
        """
        param_str = ""
        for key, value in self.content.items():
            param_str += "%s = %s\n" % (key, value)
        return param_str


class Reparsable:
    """
    Class to represent quickly parsable Cartesian configuration.

    The class produces both parser and parameters (parser dicts) on demand.
    """

    def __init__(self) -> None:
        """Initialize the parsable structure."""
        self.steps = []

    def __repr__(self) -> str:
        """Provide a representation of the parsable Cartesian configuration."""
        restriction = "Parsing parameters with the following configuration:\n"
        for step in self.steps:
            restriction += step.reportable_form()
        return restriction

    def parse_next_file(self, pfile: str) -> None:
        """
        Add a file parsing step.

        :param pfile: file to be parsed next

        If the parsable file has a relative form (not and absolute path), it
        will be searched in the relative test suite config directory.
        """
        if os.path.isabs(pfile):
            filename = pfile
        else:
            filename = os.path.join(custom_configs_dir(), pfile)
        self.steps.append(ParsedFile(filename))

    def parse_next_str(self, pstring: str) -> None:
        """
        Add a string parsing step.

        :param pstring: string to be parsed next
        """
        self.steps.append(ParsedStr(pstring))

    def parse_next_dict(self, pdict: dict[str, str]) -> None:
        """
        Add a dictionary parsing step.

        :param pdict: dictionary to be parsed next
        """
        self.steps.append(ParsedDict(pdict))

    def parse_next_batch(
        self,
        base_file: str = None,
        base_str: str | None = "",
        base_dict: dict[str, str] = None,
        ovrwrt_file: str = None,
        ovrwrt_str: str | None = "",
        ovrwrt_dict: dict[str, str] = None,
    ) -> None:
        """
        Parse a batch of base file, string, and dictionary.

        Possibly also parse a batch of an overwrite file (with custom parameters
        at the user's home location).

        :param base_file: file to be parsed first
        :param base_str: string to be parsed first
        :param base_dict: params to be added first
        :param ovrwrt_file: file to be parsed last
        :param ovrwrt_str: string to be parsed last
        :param ovrwrt_dict: params to be added last

        The priority of the setting follows the order of the arguments:
        Dictionary with some parameters is topmost, string with some
        parameters is next and the file with parameters is taken as a base.
        The overwriting version is taken last, the base version first.
        """
        if base_file:
            self.parse_next_file(base_file)
        if base_str:
            self.parse_next_str(base_str)
        if base_dict:
            self.parse_next_dict(base_dict)
        if ovrwrt_file:
            self.parse_next_file(ovrwrt_file)
        if ovrwrt_str:
            self.parse_next_str(ovrwrt_str)
        if ovrwrt_dict:
            self.parse_next_dict(ovrwrt_dict)

    def get_parser(
        self,
        show_restriction: bool = False,
        show_dictionaries: bool = False,
        show_dict_fullname: bool = False,
        show_dict_contents: bool = False,
        show_empty_cartesian_product: bool = True,
    ) -> cartesian_config.Parser:
        """
        Get a basic parameters parser with its dictionaries.

        :param show_restriction: whether to show the restriction strings
        :param show_dictionaries: whether to show the obtained variants
        :param show_dict_fullname: whether to show the variant fullname rather than its shortname
        :param show_dict_contents: whether to show the obtained variant parameters
        :param show_empty_cartesian_product: whether to check and show the resulting cartesian product

        :returns: resulting parser
        :raises: :py:class:`EmptyCartesianProduct` if no combination of the restrictions exists
        """
        parser = cartesian_config.Parser()
        hostname = os.environ.get("PREFIX", os.environ.get("HOSTNAME", "avocado"))
        parser.parse_string("hostname = %s\n" % hostname)
        suite_path = settings.as_dict().get("i2n.common.suite_path")
        parser.parse_string("suite_path = %s\n" % suite_path)
        parser.parse_string(
            "test_pre_hook = %s\n"
            % os.path.join(suite_path, "controls", "pre_test.control")
        )

        for step in self.steps:
            if isinstance(step, ParsedFile):
                parser.parse_file(step.filename)
            if isinstance(step, ParsedStr):
                parser.parse_string(step.content)
            if isinstance(step, ParsedDict):
                parser.parse_string(step.parsable_form())

        # log any required information and detect empty Cartesian product
        if show_restriction:
            logging.debug(self)
        if show_dictionaries or show_empty_cartesian_product:
            options = collections.namedtuple(
                "options", ["repr_mode", "fullname", "contents"]
            )
            peek_parser = self.get_parser(
                show_dictionaries=False, show_empty_cartesian_product=False
            )
            # break generator into first detectable entry and rest to reuse it better
            peek_generator = peek_parser.get_dicts()
            if show_empty_cartesian_product:
                try:
                    peek_dict = peek_generator.__next__()
                    if show_dictionaries:
                        cartesian_config.print_dicts(
                            options(False, show_dict_fullname, show_dict_contents),
                            (peek_dict,),
                        )
                        cartesian_config.print_dicts(
                            options(False, show_dict_fullname, show_dict_contents),
                            peek_generator,
                        )
                except StopIteration:
                    raise EmptyCartesianProduct(str(self)) from None
            else:
                cartesian_config.print_dicts(
                    options(False, show_dict_fullname, show_dict_contents),
                    peek_generator,
                )

        return parser

    def get_params(
        self,
        list_of_keys: list[str] = None,
        dict_index: int = 0,
        show_restriction: bool = False,
        show_dictionaries: bool = False,
        show_dict_fullname: bool = False,
        show_dict_contents: bool = False,
    ) -> Params:
        """
        Get a single parameter dictionary from the currently parsed configuration.

        The parameter dictionary is always validated for existence (nonempty
        Cartesian product) and uniqueness (no more than one final variant).

        :param list_of_keys: list of parameters key in the final selection
        :param int dict_index: index of the dictionary to use as parameters
        :returns: first variant dictionary from all current parsed steps
        :raises: :py:class:`AssertionError` if the parameter dictionary is not unique

        The rest of the arguments are identical to the ones from :py:method:`get_parser`.
        """
        parser = self.get_parser(
            show_restriction=show_restriction,
            show_dictionaries=show_dictionaries,
            show_dict_fullname=show_dict_fullname,
            show_dict_contents=show_dict_contents,
            show_empty_cartesian_product=True,
        )

        for i, d in enumerate(parser.get_dicts()):
            if i == dict_index:
                default_params = d
                break
        else:
            raise ValueError(
                f"There must be a configuration for the restriction:\n{self}"
            )

        if list_of_keys is None:
            selected_params = default_params
        else:
            selected_params = {key: default_params[key] for key in list_of_keys}
        return Params(selected_params)

    def get_copy(self) -> "Reparsable":
        """
        Get a copy of the current reparsable that can safely be updated further.

        :returns: a copy of self with all current parsed steps in an independent list

        The rest of the arguments are identical to the ones from :py:method:`get_parser`.
        """
        new = Reparsable()
        new.steps = copy.copy(self.steps)
        return new


###################################################################
# overwrite string and overwrite dictionary automation methods
###################################################################


def all_restrictions() -> list[str]:
    """
    Return all restrictions that can be passed for any test configuration.

    :returns: all available (from configuration) vms
    """
    rep = Reparsable()
    rep.parse_next_file("groups-base.cfg")
    return rep.get_params(list_of_keys=["main_restrictions"]).objects(
        "main_restrictions"
    )


def all_objects(key: str = "vms", composites: list[str] = None) -> list[str]:
    """
    Return all test objects that can be passed for any test configuration.

    :param: key: key to extract parametric objects from
    :param composites: composite restriction of the returned objects
    :returns: all available (from configuration) objects of a given type
    """
    rep = Reparsable()
    rep.parse_next_file("guest-base.cfg")
    params = rep.get_params()
    composites = [] if not composites else composites
    for composite in composites:
        params = params.object_params(composite)
    return params.objects(key)


def all_suffixes_by_restriction(restriction: str, key: str = "nets") -> list[str]:
    """
    Return all object suffixes via restriction of their variants.

    :param: restriction: restriction of the suffix variants
    :param: key: key to describe the parametric object type
    :returns: all restricted (from configuration) object suffixes of a given type
    """
    rep = Reparsable()
    rep.parse_next_file(f"{key}.cfg")
    rep.parse_next_str(restriction)
    parser = rep.get_parser()
    return [d["shortname"] for d in parser.get_dicts()]


def main_vm() -> str | None:
    """
    Return the default main vm that can be passed for any test configuration.

    :returns: main available (from configuration) vm
    """
    rep = Reparsable()
    rep.parse_next_file("guest-base.cfg")
    return rep.get_params(list_of_keys=["main_vm"]).get("main_vm")


def re_str(variant_str: str, base_str: str = "", tag: str = "") -> str:
    """
    Add a variant restriction to the base string, optionally adding a custom tag as well.

    :param variant_str: variant restriction
    :param base_str: string where the variant restriction will be added
    :param tag: additional tag to the variant combination
    :returns: restricted parameter string
    """
    if tag != "":
        variant_str = "variants:\n    - %s:\n        only %s\n" % (tag, variant_str)
    else:
        variant_str = "only %s\n" % variant_str
    return base_str + variant_str


def join_str(variant_strs: dict[str, str], sort_key: str, base_str: str = "") -> str:
    """
    Join all object variant restrictions over the base string.

    :param variant_strs: variant restrictions for each object as key, value pair
    :param sort_key: key to extract parametric objects from
    :param base_str: string where the variant restriction will be added
    :returns: restricted parameter string
    """
    objects, variant_str = "", ""
    available_objects = all_objects(sort_key)
    for suffix in available_objects:
        if suffix not in variant_strs.keys():
            continue
        variant = variant_strs[suffix]
        subvariant = "".join(
            ["    " + line + "\n" for line in variant.rstrip("\n").split("\n")]
        )
        variant_str += "%s:\n%s" % (suffix, subvariant)
        objects += " " + suffix
    if objects == "":
        raise ValueError(
            f"Could not find some of {list(variant_strs.keys())} among "
            f"the available {available_objects}"
        )
    variant_str += "join" + objects + "\n"
    return base_str + variant_str
