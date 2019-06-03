.. _cartesian_configuration:

=======================
Cartesian Configuration
=======================

In software testing, key/value pairs are usually used as test input parameters.

Cartesian product is a mathematical operation which creates a set from
multiple sets. Given sets A and B, the cartesian product of both is
the set of all ordered pairs (a,b) where a belongs to A and b belongs to B.

In Avocado VT, cartesian configuration is a method of defining key/value pairs
which are later combined using the cartesian product concept. Each element of
this product is used as input by a different test execution. The product can
be filtered and adjusted prior to testing, with filters, dependencies, and
key/value substitutions.

The parser relies on indentation, and is very sensitive to misplacement
of tab and space characters. It’s highly recommended to edit/view
Cartesian configuration files in an editor capable of collapsing tab
characters into four space characters. Improper attention to column
spacing can drastically affect output.

.. _keys_and_values:

Keys and values
===============

Keys and values are the most basic useful facility provided by the
format. A statement in the form ``<key> = <value>`` sets ``<key>`` to
``<value>``. Values are strings, terminated by a linefeed, with
surrounding quotes completely optional (but honored). A reference of
descriptions for most keys is included in section Configuration Parameter
Reference.
However, key precedence is evaluated in top-down or ‘last defined’
order. In other words, the last parsed key has precedence over earlier
definitions.

.. _variants:

Variants
========

A variant is a named list of key/value pairs. A variant set is a list of
variants. The cartesian configuration parser reads a cartesian configuration
file and creates a cartesian product of variant sets; the number of
combinations is the multiplication of the number of variants in each variant
set, each combination is a tuple and the number of elements in this tuple is
equal to the number of variant sets. Eg. if variant sets A and B have 3 and 4
variants respectively, their cartesian product will have 3 x 4 = 12 tuples of
2 elements.

A variant contains key-value pairs. Each ordered variant tuple in the cartesian
product defines a ordered list of key-value pairs definitions. The ordered execution
of these definitions creates a dictionary (a list of key/value pairs in which
each key appears just once).

In a cartesian configuration file, a variant set is defined using the ‘variants’
block, which is opened by a ‘variants:’ statement. The contents of the block
must be indented further right than the ‘variants:’ statement.  Each variant is
defined using a ‘<variant_name>:‘ statement. For example::

    variants:
        - one:
            key1 = Hello
        - two:
            key2 = World
        - three:
    variants:
        - four:
            key3 = foo
        - five:
            key3 = bar
        - six:
            key1 = foo
            key2 = bar

While combining variant sets, the parser creates names for each combination
prepending each variant to a list. In other words, the first variant name parsed
will appear as the right most name component. This list may be represented with
a string with the '.' character between each component name. For example, running
``cartesian_config.py`` against the content above produces the following
combinations and names::

    dict    1:  four.one
    dict    2:  four.two
    dict    3:  four.three
    dict    4:  five.one
    dict    5:  five.two
    dict    6:  five.three
    dict    7:  six.one
    dict    8:  six.two
    dict    9:  six.three

Dict 1 elements::

    key1 = Hello
    key3 = foo

Dict 7 elements::

    key1 = foo
    key2 = bar

.. _dependencies:

Dependencies
============

Often it is necessary to dictate relationships between variants. In this
way, the order of the resulting variant sets may be influenced. This is
accomplished by listing the names of all parents (in order) after the
child’s variant name. However, the influence of dependencies is ‘weak’,
in that any later defined, lower-level (higher indentation) definitions,
and/or filters (see section filters_) can remove or modify dependents. For
example, if testing unattended installs, each virtual machine must be booted
before, and shutdown after:

::

    variants:
        - one:
            key1 = Hello
        - two: one
            key2 = World
        - three: one two

Results in the correct sequence of variant sets: one, two, *then* three.


.. _filters:

Variant set combination filters
===============================

Filters allow specifying a subset of all variant set combinations. Names are
matched by combining variant names with one of the character(s) below:

* ‘,’ : OR operator
* ‘..’ : AND operator
* ‘.’ : immediately followed by

Considering the list of variant set combinations below::

    Linux.x86.OpenSuse
    Linux.x86.Debian
    Linux.OpenSuse

The filter::

    Linux..OpenSuse

matches the following combinations::

    Linux.x86.OpenSuse
    Linux.OpenSuse

The filter::

    Linux.OpenSuse

matches the following combinations::

    Linux.OpenSuse

The filter::

    Linux.OpenSuse,Linux..Debian

matches the following combinations::

    Linux.OpenSuse
    Linux.x86.Debian

Filters can be used in 3 ways:

1. include only combinations names matching a pattern. Requires keyword 'only'
Useful to limit the combinations list size when there is an extremely large matrix
of variants.

Example::

    variants:
        - one:
            key1 = Hello
    variants:
        - two:
            key2 = Complicated
        - three: one two
            key3 = World
    variants:
        - default:
            only three
            key2 =

    only default

Results in the following:

::

    dict 1: default.three.one
      key1 = Hello
      key2 =
      key3 = World


2. exclude all combinations names not matching a pattern. Requires keyword 'no'
Useful to remove particular conflicting key/value pairs from some combinations.

Example::

    key1 = value1
    key2 = value2

    variants:
        - one:
            key1 = Hello World
            key2 = foo1
        - two:
            key2 = foo2
        - three:

    variants:
        - A:
            no one

Results in the following::

    Dict 1: A.two
        key1 = value1
        key2 = foo1
    Dict 2: A.three
        key1 = value1
        key2 = value2


3. update key/value pairs of combinations names matching a pattern

Example::

    variants:
        - OpenSuse
            initrd = b
        - Debian
            initrd = c
    variants:
        - Linux:
            initrd = a

    Linux..OpenSuse:
    initrd = initrd

Results in the following::

    dict 1: Linux.Debian
      initrd = c
    dict 2: Linux.OpenSuse
      initrd = initrd_value

Thus, this sets the ‘initrd’ key to ‘initrd_value’ in all combinations containing
‘Linux’ followed (immediately or not) by ‘OpenSuse’.

However, note that any of these filters may be used within variants as well.
In this case, they are only evaluated when that variant name is
selected for inclusion (implicitly or explicitly) by a higher-order.


.. _value_substitutions:

Value Substitutions
===================

Value substitution allows for selectively overriding precedence and
defining part or all of a future key’s value. Using a previously defined
key, it’s value may be substituted in or as a another key’s value. The
syntax is exactly the same as in the bash shell, where as a key’s value
is substituted in wherever that key’s name appears following a ‘$’
character. When nesting a key within other non-key-name text, the name
should also be surrounded by ‘{‘, and ‘}’ characters.

Replacement is context-sensitive, thereby if a key is redefined within
the same, or, higher-order block, that value will be used for future
substitutions. If a key is referenced for substitution, but hasn’t yet
been defined, no action is taken. In other words, the $key or ${key}
string will appear literally as or within the value. Nesting of
references is not supported (i.e. key substitutions within other
substitutions.

For example, if ``one = 1, two = 2, and three = 3``; then,
``order = ${one}${two}${three}`` results in ``order = 123``. This is
particularly handy for rooting an arbitrary complex directory tree
within a predefined top-level directory.

An example of context-sensitivity,

::

    key1 = default value
    key2 = default value

    sub = "key1: ${key1}; key2: ${key2};"

    variants:
        - one:
            key1 = Hello
            sub = "key1: ${key1}; key2: ${key2};"
        - two: one
            key2 = World
            sub = "key1: ${key1}; key2: ${key2};"
        - three: one two
            sub = "key1: ${key1}; key2: ${key2};"

Results in the following,

::

    dict    1:  one
        dep = []
        key1 = Hello
        key2 = default value
        name = one
        shortname = one
        sub = key1: Hello; key2: default value;
    dict    2:  two
        dep = ['one']
        key1 = default value
        key2 = World
        name = two
        shortname = two
        sub = key1: default value; key2: World;
    dict    3:  three
        dep = ['one', 'two']
        key1 = default value
        key2 = default value
        name = three
        shortname = three
        sub = key1: default value; key2: default value;


.. _key_sub_arrays:

Key sub-arrays
==============

Parameters for objects like VM’s utilize array’s of keys specific to a
particular object instance. In this way, values specific to an object
instance can be addressed. For example, a parameter ‘vms’ lists the VM
objects names to instantiate in the current frame’s test. Values specific
to one of the named instances should be prefixed to the name:

::

    vms = vm1 second_vm another_vm
    mem = 128
    mem_vm1 = 512
    mem_second_vm = 1024

The result would be, three virtual machine objects are create. The third
one (another\_vm) receives the default ‘mem’ value of 128. The first two
receive specialized values based on their name.

The order in which these statements are written in a configuration file
is not important; statements addressing a single object always override
statements addressing all objects. Note: This is contrary to the way the
Cartesian configuration file as a whole is parsed (top-down).

.. _include_statements:

Include statements
==================

The ‘``include``’ statement is utilized within a Cartesian configuration
file to better organize related content. When parsing, the contents of
any referenced files will be evaluated as soon as the parser encounters
the ``include`` statement. The order in which files are included is
relevant, and will carry through any key/value substitutions
(see section key_sub_arrays_) as if parsing a complete, flat file.


.. developing_configurations:

Developing cartesian configurations
===================================

The parser is available as both a Python module and command line tool
for examining the cartesian configuration parsing results in a text
output. To use it on the command line, run the module followed by the path of
the cartesian configuration file to parse. For example,
``virttest/cartesian_config.py tests/libvirt/tests.cfg``.

The output will be just the names of the variants sets combinations.
However, the ‘``--contents``’ parameter may be specified to examine the output
in more depth. The key/value data is stored as a Python dict-like object,
the collection of dictionaries is displayed as a Python list-like object
and the tool output reflects that. Running this tool from the command line
is an excellent method for both reviewing and learning about the Cartesian
Configuration format.

When examining Cartesian configuration files, it is helpful to consider the
earliest key definitions as “defaults”, then look to the end of the file for
other top-level override to those values. If in doubt of where to define
a key, placing it at the top indentation level  at the end of the file, will
guarantee it is used.

Advanced features
=================

Variant sets combinations short names
-------------------------------------

Variant set combinations names can become quite long and, due to this, a
'short name' is also automatically created by the test framework. For
convenience, variants which name begins with a ‘``@``’ do not prepend their
name to 'short name', only 'name'. This allows creating ‘shortcuts’ for
specifying multiple sets or changes to key/value pairs without changing
the results directory name. For example, this is often convenient for
providing a collection of related pre-configured tests based on a
combination of others.

::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

    variants:
        - @A:
            no one
        - B:
            only one,three

Results in the following::

    Dictionary #0:
        depend = ['A.one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = A.two
        shortname = two
    Dictionary #1:
        depend = ['A.one', 'A.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = A.three
        shortname = three
    Dictionary #2:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = B.one
        shortname = B.one
    Dictionary #3:
        depend = ['B.one', 'B.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = B.three
        shortname = B.three


Named variant set
-----------------

It is possible to assign a name to a variant set.  This enables an entire
variant set to be used in filters_. All variant set combinations will contain an
extra key/value pair for each named variant set it contains, the key is
the variant set name and the value is the corresponding current variant name.
For example::

   variants var1_name:
        - one:
            key1 = Hello
        - two:
            key2 = World
        - three:
   variants var2_name:
        - one:
            key3 = Hello2
        - two:
            key4 = World2
        - three:

   only (var2_name=one).(var1_name=two)

Results in the following when parsed with ``cartesian_config.py -c``::

    dict    1:  (var2_name=one).(var1_name=two)
          dep = []
          key2 = World         # variable key2 from variants var1_name and variant two.
          key3 = Hello2        # variable key3 from variants var2_name and variant one.
          name = (var2_name=one).(var1_name=two)
          shortname = (var2_name=one).(var1_name=two)
          var1_name = two      # variant name in same namespace as variables.
          var2_name = one      # variant name in same namespace as variables.

Named variants could also be used as normal variables.::

   variants guest_os:
        - fedora:
        - ubuntu:
   variants disk_interface:
        - virtio:
        - hda:

Results in the following::

    dict    1:  (disk_interface=virtio).(guest_os=fedora)
        dep = []
        disk_interface = virtio
        guest_os = fedora
        name = (disk_interface=virtio).(guest_os=fedora)
        shortname = (disk_interface=virtio).(guest_os=fedora)
    dict    2:  (disk_interface=virtio).(guest_os=ubuntu)
        dep = []
        disk_interface = virtio
        guest_os = ubuntu
        name = (disk_interface=virtio).(guest_os=ubuntu)
        shortname = (disk_interface=virtio).(guest_os=ubuntu)
    dict    3:  (disk_interface=hda).(guest_os=fedora)
        dep = []
        disk_interface = hda
        guest_os = fedora
        name = (disk_interface=hda).(guest_os=fedora)
        shortname = (disk_interface=hda).(guest_os=fedora)
    dict    4:  (disk_interface=hda).(guest_os=ubuntu)
        dep = []
        disk_interface = hda
        guest_os = ubuntu
        name = (disk_interface=hda).(guest_os=ubuntu)
        shortname = (disk_interface=hda).(guest_os=ubuntu)

Implicit keys
-------------

Some special keys are expected to be defined with a list of values and
implicitly define a set of keys for each one of its values. For example, each
value of the 'vms' key will implicitly define keys such as 'mem_<vm>'.
In this case a default 'mem' key is also available. Example::

    vms = vm1 second_vm another_vm
    mem = 128
    mem_vm1 = 512
    mem_second_vm = 1024

As result, 3 virtual machine objects are created with the following
amount of memory::

    vm1: 512
    second_vm: 1024
    another_vm: 128 (default)

The order in which these statements are written in a configuration file
is not important. Assignments to a single object always override assignments
to all objects. Note: This is contrary to the way the Cartesian configuration
file as a whole is parsed (top-down).


.. _formal_definition:

Formal definition
=================

-  A list of dictionaries is referred to as a frame.

-  The parser produces a list of dictionaries (dicts). Each dictionary
   contains a set of key-value pairs.

-  Each dict contains at least three keys: name, shortname and depend.
   The values of name and shortname are strings, and the value of depend
   is a list of strings.

-  The initial frame contains a single dict, whose name and shortname
   are empty strings, and whose depend is an empty list.

-  Parsing dict contents

   -  The dict parser operates on a frame, referred to as the current frame.

   -  A statement of the form <key> = <value> sets the value of <key> to
      <value> in all dicts of the current frame. If a dict lacks <key>,
      it will be created.

   -  A statement of the form <key> += <value> appends <value> to the
      value of <key> in all dicts of the current frame. If a dict lacks
      <key>, it will be created.

   -  A statement of the form <key> <= <value> pre-pends <value> to the
      value of <key> in all dicts of the current frame. If a dict lacks
      <key>, it will be created.

   -  A statement of the form <key> ?= <value> sets the value of <key>
      to <value>, in all dicts of the current frame, but only if <key>
      exists in the dict. The operators ?+= and ?<= are also supported.

   -  A statement of the form no <regex> removes from the current frame
      all dicts whose name field matches <regex>.

   -  A statement of the form only <regex> removes from the current
      frame all dicts whose name field does not match <regex>.

-  Content exceptions

   -  Single line exceptions have the format <regex>: <key> <operator>
      <value> where <operator> is any of the operators listed above
      (e.g. =, +=, ?<=). The statement following the regular expression
      <regex> will apply only to the dicts in the current frame whose
      name partially matches <regex> (i.e. contains a substring that
      matches <regex>).

   -  A multi-line exception block is opened by a line of the format
      <regex>:. The text following this line should be indented. The
      statements in a multi-line exception block may be assignment
      statements (such as <key> = <value>) or no or only statements.
      Nested multi-line exceptions are allowed.

-  Parsing Variants

   -  A variants block is opened by a ``variants:`` statement. The indentation
      level of the statement places the following set within the outer-most
      context-level when nested within other ``variant:`` blocks.  The contents
      of the ``variants:`` block must be further indented.

   -  A variant-name may optionally follow the ``variants`` keyword, before
      the ``:`` character.  That name will be inherited by and decorate all
      block content as the key for each variant contained in it's the
      block.

   -  The name of the variants are specified as ``- <variant_name>:``.
      Each name is pre-pended to the name field of each dict of the variant's
      frame, along with a separator dot ('.').

   -  The contents of each variant may use the format ``<key> <op> <value>``.
      They may also contain further ``variants:`` statements.

   -  If the name of the variant is not preceeded by a @ (i.e. -
      @<variant\_name>:), it is pre-pended to the shortname field of
      each dict of the variant's frame. In other words, if a variant's
      name is preceeded by a @, it is omitted from the shortname field.

   -  Each variant in a variants block inherits a copy of the frame in
      which the variants: statement appears. The 'current frame', which
      may be modified by the dict parser, becomes this copy.

   -  The frames of the variants defined in the block are
      joined into a single frame.  The contents of frame replace the
      contents of the outer containing frame (if there is one).

-  Filters

   -  Filters can be used in 3 ways:

      -  ::

             only <filter>

      -  ::

             no <filter>

      -  ::

             <filter>: starts a conditional block (see section :ref:`filters_`)

   -  Syntax:

::

    .. means AND
    . means IMMEDIATELY-FOLLOWED-BY

-  Example:

   ::

       qcow2..Fedora.14, RHEL.6..raw..boot, smp2..qcow2..migrate..ide

::

    means match all dicts whose names have:
    (qcow2 AND (Fedora IMMEDIATELY-FOLLOWED-BY 14)) OR
    ((RHEL IMMEDIATELY-FOLLOWED-BY 6) AND raw AND boot) OR
    (smp2 AND qcow2 AND migrate AND ide)

-  Note:

   ::

       'qcow2..Fedora.14' is equivalent to 'Fedora.14..qcow2'.

::

    'qcow2..Fedora.14' is not equivalent to 'qcow2..14.Fedora'.
    'ide, scsi' is equivalent to 'scsi, ide'.


.. _examples_cartesian:

Examples
========

-  A single dictionary::

    key1 = value1
    key2 = value2
    key3 = value3

    Results in the following::

    Dictionary #0:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name =
        shortname =

-  Adding a variants block::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
        - two:
        - three:

   Results in the following::

    Dictionary #0:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name = one
        shortname = one
    Dictionary #1:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name = two
        shortname = two
    Dictionary #2:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name = three
        shortname = three

-  Modifying dictionaries inside a variant::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two:
            key2 <= another_prefix_
        - three:

   Results in the following::

    Dictionary #0:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = one
        shortname = one
    Dictionary #1:
        depend = []
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = two
        shortname = two
    Dictionary #2:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name = three
        shortname = three

-  Adding dependencies::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

   Results in the following::

    Dictionary #0:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = one
        shortname = one
    Dictionary #1:
        depend = ['one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = two
        shortname = two
    Dictionary #2:
        depend = ['one', 'two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = three
        shortname = three

-  Multiple variant blocks::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

    variants:
        - A:
        - B:

   Results in the following::

    Dictionary #0:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = A.one
        shortname = A.one
    Dictionary #1:
        depend = ['A.one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = A.two
        shortname = A.two
    Dictionary #2:
        depend = ['A.one', 'A.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = A.three
        shortname = A.three
    Dictionary #3:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = B.one
        shortname = B.one
    Dictionary #4:
        depend = ['B.one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = B.two
        shortname = B.two
    Dictionary #5:
        depend = ['B.one', 'B.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = B.three
        shortname = B.three

-  Filters, ``no`` and ``only``::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

    variants:
        - A:
            no one
        - B:
            only one,three

   Results in the following::

    Dictionary #0:
        depend = ['A.one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = A.two
        shortname = A.two
    Dictionary #1:
        depend = ['A.one', 'A.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = A.three
        shortname = A.three
    Dictionary #2:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = B.one
        shortname = B.one
    Dictionary #3:
        depend = ['B.one', 'B.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = B.three
        shortname = B.three

-  Exceptions::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

    variants:
        - @A:
            no one
        - B:
            only one,three

    three: key4 = some_value

    A:
        no two
        key5 = yet_another_value

   Results in the following::

    Dictionary #0:
        depend = ['A.one', 'A.two']
        key1 = value1
        key2 = value2
        key3 = value3
        key4 = some_value
        key5 = yet_another_value
        name = A.three
        shortname = three
    Dictionary #1:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = B.one
        shortname = B.one
    Dictionary #2:
        depend = ['B.one', 'B.two']
        key1 = value1
        key2 = value2
        key3 = value3
        key4 = some_value
        name = B.three
        shortname = B.three


.. _default_configuration_files:

Default Configuration Files
===========================

The test configuration files are used for controlling the framework, by
specifying parameters for each test. The parser produces a list of
key/value sets, each set pertaining to a single test. Variants are
organized into separate files based on scope and/or applicability. For
example, the definitions for guest operating systems is sourced from a
shared location since all virtualization tests may utilize them.

For each set/test, keys are interpreted by the test dispatching system,
the pre-processor, the test module itself, then by the post-processor.
Some parameters are required by specific sections and others are
optional. When required, parameters are often commented with possible
values and/or their effect. There are select places in the code where
in-memory keys are modified, however this practice is discouraged unless
there’s a very good reason.

When ``avocado vt-bootstrap --vt-type [type]`` is executed
(see section :ref:`run_bootstrap`), copies of the
sample configuration files are copied for use under the ``backends/[type]/cfg`` subdirectory of
the virtualization technology-specific directory.  For example, ``backends/qemu/cfg/base.cfg``.

+-----------------------------+-------------------------------------------------+
| Relative Directory or File  | Description                                     |
+-----------------------------+-------------------------------------------------+
| cfg/tests.cfg               | The first file read that includes all other     |
|                             | files, then the master set of filters to select |
|                             | the actual test set to be run.  Normally        |
|                             | this file never needs to be modified unless     |
|                             | precise control over the test-set is needed     |
|                             | when utilizing the autotest-client (only).      |
+-----------------------------+-------------------------------------------------+
| cfg/tests-shared.cfg        | Included by ``tests.cfg`` to indirectly         |
|                             | reference the remaining set of files to include |
|                             | as well as set some global parameters.          |
|                             | It is used to allow customization and/or        |
|                             | insertion within the set of includes. Normally  |
|                             | this file never needs to be modified.           |
+-----------------------------+-------------------------------------------------+
| cfg/base.cfg                | Top-level file containing important parameters  |
|                             | relating to all tests.  All keys/values defined |
|                             | here will be inherited by every variant unless  |
|                             | overridden.  This is the *first* file to check  |
|                             | for settings to change based on your environment|
+-----------------------------+-------------------------------------------------+
| cfg/build.cfg               | Configuration specific to pre-test code         |
|                             | compilation where required/requested. Ignored   |
|                             | when a client is not setup for build testing.   |
+-----------------------------+-------------------------------------------------+
| cfg/subtests.cfg            | Automatically generated based on the test       |
|                             | modules and test configuration files found      |
|                             | when the ``avocado vt-bootstrap`` is used.      |
|                             | Modifications are discouraged since they will   |
|                             | be lost next time bootstrap is used.            |
+-----------------------------+-------------------------------------------------+
| cfg/guest-os.cfg            | Automatically generated when                    |
|                             | ``avocado vt-bootstrap`` is used from           |
|                             | files within ``shared/cfg/guest-os/``.  Defines |
|                             | all supported guest operating system            |
|                             | types, architectures, installation images,      |
|                             | parameters, and disk device or image names.     |
+-----------------------------+-------------------------------------------------+
| cfg/guest-hw.cfg            | All virtual and physical hardware related       |
|                             | parameters are organized within variant names.  |
|                             | Within subtest variants or the top-level test   |
|                             | set definition, hardware is specified by        |
|                             | Including, excluding, or filtering variants and |
|                             | keys established in this file.                  |
+-----------------------------+-------------------------------------------------+
| cfg/cdkeys.cfg              | Certain operating systems require non-public    |
|                             | information in order to operate and or install  |
|                             | properly. For example, installation numbers and |
|                             | license keys. None of the values in this file   |
|                             | are populated automatically. This file should   |
|                             | be edited to supply this data for use by the    |
|                             | unattended install test.                        |
+-----------------------------+-------------------------------------------------+
| cfg/virtio-win.cfg          | Paravirtualized hardware when specified for     |
|                             | Windows testing, must have dependent drivers    |
|                             | installed as part of the OS installation        |
|                             | process. This file contains mandatory variants  |
|                             | and keys for each Windows OS version,           |
|                             | specifying the host location and installation   |
|                             | method for each driver.                         |
+-----------------------------+-------------------------------------------------+
