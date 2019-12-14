.. _cartesian_configuration:

=======================
Cartesian Configuration
=======================

Cartesian Configuration is a highly specialized way of providing lists
of key/value pairs within combination's of various categories. The
format simplifies and condenses highly complex multidimensional arrays
of test parameters into a flat list. The combinatorial result can be
filtered and adjusted prior to testing, with filters, dependencies, and
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
The key will become part of all lower-level (i.e. further indented) variant
stanzas (see section variants_).
However, key precedence is evaluated in top-down or ‘last defined’
order. In other words, the last parsed key has precedence over earlier
definitions.


.. _variants:

Variants
========

A ‘variants’ stanza is opened by a ‘variants:’ statement. The contents
of the stanza must be indented further left than the ‘variants:’
statement. Each variant stanza or block defines a single dimension of
the output array. When a Cartesian configuration file contains
two variants stanzas, the output will be all possible combination's of
both variant contents. Variants may be nested within other variants,
effectively nesting arbitrarily complex arrays within the cells of
outside arrays.  For example::

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

While combining, the parser forms names for each outcome based on
prepending each variant onto a list. In other words, the first variant
name parsed will appear as the left most name component. These names can
become quite long, and since they contain keys to distinguishing between
results, a 'short-name' key is also used.  For example, running
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

Variant shortnames represent the <TESTNAME> value used when results are
recorded (see section Job Names and Tags. For convenience
variants who’s name begins with a ‘``@``’ do not prepend their name to
'short-name', only 'name'. This allows creating ‘shortcuts’ for
specifying multiple sets or changes to key/value pairs without changing
the results directory name. For example, this is often convenient for
providing a collection of related pre-configured tests based on a
combination of others.


Named variants
==============

Named variants allow assigning a parseable name to a variant set.  This enables
an entire variant set to be used for in filters_.  All output combinations will
inherit the named variant key, along with the specific variant name.  For example::

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

Results in the following outcome when parsed with ``cartesian_config.py -c``::

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

Which then results in the following::

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

Filters
=======

Filter statements allow modifying the resultant set of keys based on the
name of the variant set (see section variants_). Filters can be used in 3 ways:
Limiting the set to include only combination names matching a pattern.
Limiting the set to exclude all combination names not matching a
pattern. Modifying the set or contents of key/value pairs within a
matching combination name.

Names are matched by pairing a variant name component with the
character(s) ‘,’ meaning OR, ‘..’ meaning AND, and ‘.’ meaning
IMMEDIATELY-FOLLOWED-BY. When used alone, they permit modifying the list
of key/values previously defined. For example:

::

    Linux..OpenSuse:
    initrd = initrd

Modifies all variants containing ‘Linux’ followed anywhere thereafter
with ‘OpenSuse’, such that the ‘initrd’ key is created or overwritten
with the value ‘initrd’.

When a filter is preceded by the keyword ‘only’ or ‘no’, it limits the
selection of variant combination's This is used where a particular set
of one or more variant combination's should be considered selectively or
exclusively. When given an extremely large matrix of variants, the
‘only’ keyword is convenient to limit the result set to only those
matching the filter. Whereas the ‘no’ keyword could be used to remove
particular conflicting key/value sets under other variant combination
names. For example:

::

    only Linux..Fedora..64

Would reduce an arbitrarily large matrix to only those variants who’s
names contain Linux, Fedora, and 64 in them.

However, note that any of these filters may be used within named
variants as well. In this application, they are only evaluated when that
variant name is selected for inclusion (implicitly or explicitly) by a
higher-order. For example:

::

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

Results in the following outcome:

::

    name = default.three.one
    key1 = Hello
    key2 =
    key3 = World


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


.. _heterogeneous_guest_variants:

Heterogeneous guest variants
============================

The ‘``join``’ filter combined with the ‘``suffix``’ operator can be utilized
together in order to produce guest variants with different guest OS or other
types of configuration within the same test. Adding the ‘``suffix``’ keyword
at the end of each variant to be combined and joining all the variants in the
end will produce one final variant product with all participating variant
dictionaries separately suffixed and combined into one final dictionary. For
instance the following definition

::

    variants:
        - one:
            key1 = Hello
            key2 = Brave
            suffix _v1
        - two:
            key1 = Bye
            key2 = Brave
            key3 = World
            suffix _v2
        - three:
    variants:
        - four:
            key4 = foo
            only one
        - five:
            key4 = bar
        - six:
            key1 = foo
            key2 = bar
            key3 = baz
            only two

    join one two

will join variants ``one`` and ``two`` with suffixed parameters
``key1_v1 = Hello`` and ``key1_v2 = Bye`` in each of the following resulting
dictionaries:

::

    dict    1:  four.one.five.two
        dep = []
        key1_v1 = Hello
        key1_v2 = Bye
        key2 = Brave
        key3 = World
        key4 = bar
        name = four.one.five.two
        shortname = four.one.five.two
    dict    2:  four.one.six.two
        dep = []
        key1 = foo
        key1_v1 = Hello
        key1_v2 = Bye
        key2 = bar
        key2_v1 = Brave
        key2_v2 = Brave
        key3 = baz
        key3_v2 = World
        key4 = foo
        name = four.one.six.two
        shortname = four.one.six.two
    dict    3:  five.one.two
        dep = []
        key1_v1 = Hello
        key1_v2 = Bye
        key2 = Brave
        key3 = World
        key4 = bar
        name = five.one.two
        shortname = five.one.two
    dict    4:  five.one.six.two
        dep = []
        key1 = foo
        key1_v1 = Hello
        key1_v2 = Bye
        key2 = bar
        key2_v1 = Brave
        key2_v2 = Brave
        key3 = baz
        key3_v2 = World
        key4 = bar
        name = five.one.six.two
        shortname = five.one.six.two

Regarding the choice of variants, using the ``join one two`` also plays the
role of a filter for ``three`` which restricts the final selection to all
joined ``one``-``two`` test variants. The ``join one`` operation is thus
equivalent to an ``only one`` filter. The outcome above is additionally
filtered by ``only`` filters, which restrict the initial joined Cartesian
products:

::

    dict    1:  four.one.two
    dict    2:  four.one.five.two
    dict    3:  four.one.six.two
    dict    4:  five.one.four.two
    dict    5:  five.one.two
    dict    6:  five.one.six.two
    dict    7:  six.one.four.two
    dict    8:  six.one.five.two
    dict    9:  six.one.two

of pairs ``<four-or-five-or-six>.one`` and ``<four-or-five-or-six>.two`` to
variants containing ``four.one``, ``six.two``, or ``five.<one-or-two>``

::

    dict    1:  four.one.five.two
    dict    2:  four.one.six.two
    dict    3:  five.one.two
    dict    4:  five.one.six.two

One important point to consider when using heterogeneous variants is that
parameter overwriting of suffixed parameters is only possible using regex
operators like ‘``?=``’, ‘``?<=``’, and ‘``?+=``’. Since adding a suffix will
transform all parameters within the variant (or at least the ones that have
more general nonsuffixed version of different value), regular overwriting will
only match the general parameter and will not perform a search for the suffixed
versions for performance reasons. Using the above operators with proper regular
expression for the key will solve this.


.. _include_statements:

Include statements
==================

The ‘``include``’ statement is utilized within a Cartesian configuration
file to better organize related content. When parsing, the contents of
any referenced files will be evaluated as soon as the parser encounters
the ``include`` statement. The order in which files are included is
relevant, and will carry through any key/value substitutions
(see section key_sub_arrays_) as if parsing a complete, flat file.


.. _combinatorial_outcome:

Combinatorial outcome
=====================

The parser is available as both a python module and command-line tool
for examining the parsing results in a text-based listing. To utilize it
on the command-line, run the module followed by the path of the
configuration file to parse. For example,
``common_lib/cartesian_config.py tests/libvirt/tests.cfg``.

The output will be just the names of the combinatorial result set items
(see short-names, section Variants). However,
the ‘``--contents``’ parameter may be specified to examine the output in
more depth. Internally, the key/value data is stored/accessed similar to
a python dictionary instance. With the collection of dictionaries all
being part of a python list-like object. Irrespective of the internals,
running this module from the command-line is an excellent tool for both
reviewing and learning about the Cartesian Configuration format.

In general, each individual combination of the defined variants provides
the parameters for a single test. Testing proceeds in order, through
each result, passing the set of keys and values through to the harness
and test code. When examining Cartesian configuration files, it’s
helpful to consider the earliest key definitions as “defaults”, then
look to the end of the file for other top-level override to those
values. If in doubt of where to define or set a key, placing it at the
top indentation level, at the end of the file, will guarantee it is
used.


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

   -  A statement of the form <key> ~= <value> sets the value of <key>
      to <value> in all dicts of the current frame unless the <key> was
      already defined. Otherwise the original value is preserved.

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

-  Short-names::

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
