User Guide
==========
The primary interface are the |WHPNames| and |CFStandardNames| objects.
We will focus mostly on the |WHPNames| object.

The WHPNames Collection
-----------------------

Importing
`````````
The actual database is loaded in a lazy way, so the initial import should be fast.

>>> from cchdo.params import WHPNames
>>> WHPNames
<cchdo.params._WHPNames object at 0x7f0e853ebac0>


Name Lookups
````````````
These objects follow the standard python Mapping (e.g. dict) interface.
Exchange parameters are looked up via ODV style PARAM [UNIT] strings, optionally omitting the [UNIT] part for unitless parameters.
If the parameter is unitless, the following varations will work: [], [None], [nan] (any capitalization)

The name grammer is as follows, with {} being used for optional parts and | for exclusive or.

``PARAM{ [UNIT]}{_ALT_n}{_FLAG_W|_URL}``

>>> WHPNames["EXPOCODE"]
WHPName("EXPOCODE")
>>> WHPNames["CTDPRS [DBAR]"]
WHPName("CTDPRS [DBAR]")

Aliases will return their canonical parameter object

>>> WHPNames["CTDPRS [DBARS]"] # note the "s" at the end of the unit
WHPName("CTDPRS [DBAR]")

Aliases know where they came from
>>> WHPNames["CTDPRS [DBARS]"].whp_alias # again note the 's'
'CTDPRS [DBARS]'

.. warning::
  The uncertainty names are a lookup table and not parsed name grammer.
  This means they behave as though they are a base name.
  For example, the error name for ``D15N_NO3 [/MILLE]`` would be ``D15N_NO3_ERROR [/MILLE]`` and not ``D15N_NO3 [/MILLE]_ERROR``

  We have plans to change this to be grammer and alias all the historic names, but it is uncertain when this would be worked on.

.. warning::
  Currently the keys are case sensitive.

  >>> WHPNames["ExpoCode"]
  Traceback (most recent call last):
    File "<stdin>", line 1, in <module>
    File "/workspaces/params/cchdo/params/__init__.py", line 406, in __getitem__
      return self._cached_dict[key]
  KeyError: 'ExpoCode'

.. danger::
  The ``units`` part of the key is expected to be the WHP unit for the parameter.
  This may deviate from the actual units associated with the parameters physical dimensions.

  For example, practical salinity is a dimensionless quantity.
  In the SI system this is said to have the unit one with the symbol 1.
  See section 2.3.3 of [BIPM2019]_.
  You will see the value of 1 in the units attribute of netCDF files.
  However, in WPH Exchange files, the correct unit for practical salinity is PSS-78.

  >>> WHPNames["CTDSAL [PSS-78]"]
  WHPName("CTDSAL [PSS-78]")
  >>> WHPNames["CTDSAL [PSS-78]"].cf_unit
  '1'

Dict-like operations
````````````````````

Since |WHPNames| follows the python Mapping interface, you can do all the standard dict operations on it.

Membership tests:

>>> "CTDSAL [PSS-78]" in WHPNames
True

Dimensionless membership tests also work:

>>> "EXPOCODE" in WHPNames
True

The full parameter space is checked for membership, so the following works:

>>> "EXPOCODE_ALT_1" in WHPNames
True

Even though this is not directly in the keys:

>>> "EXPOCODE_ALT_1" in WHPNames.keys()
False

Iterating the keys will always return the keys in their ``param [unit]`` form, with the [unit] omitted if unitless.

>>> for key in WHPNames:
...   print(key)
...   break
...
EXPOCODE

The views returned by `.items()`, `.values()`, and `.keys()` also work as expected.


|WHPName| Groups
````````````````
There are some groupings of parameters that are very useful when translating to netCDF, specifically when determining the shape of the variables.
The idea was as follows: cruise level parameters would be scalar variables, profile level parameters would be single dimensional, and sample level parameters (e.g. bottle sample measurements) would be two or more dimensional.
These groupings are provided by a `.groups` property as a named tuple.

>>> WHPNames.groups
WHPNameGroups(cruise=frozenset(), profile=frozenset( [...]

This named tuple has the names: ``cruise``, ``profile``, and ``sample`` which all contained frozen sets of |WHPName| instances.


.. |WHPNames| replace:: :data:`~cchdo.params.WHPNames`
.. |WHPName| replace:: :data:`~cchdo.params.WHPName`
.. |CFStandardNames| replace:: :data:`~cchdo.params.CFStandardNames`

.. [BIPM2019] BIPM. Le Système international d'unités / The International System of Units ('The SI Brochure'). Bureau international des poids et mesures, ninth edition, 2019. URL https://www.bipm.org/en/publications/si-brochure, ISBN 978-92-822-2272-0
