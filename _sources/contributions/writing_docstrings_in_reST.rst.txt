Writing Docstrings in reStructuredText (reST)
=============================================

This guide explains how to write high‑quality Python docstrings using
reStructuredText (reST) so they render well with Sphinx and are picked up by
``autodoc``. The guidelines apply to both Python 2 and Python 3 code in this
repository.

For more information, please refer to the `Sphinx documentation <https://www.sphinx-doc.org/en/master/usage/restructuredtext/index.html>`__ .

Core principles
---------------

For module, class, and function docstrings, follow these core principles:

- Write a short, imperative summary line on the first line, ending with a period.
- Leave one blank line after the summary, then provide details.
- **Give an example usage if helpful**
    - You don't need to go crazy here, only if it's really helpful or necessary.

For class and moreso function docstrings, follow these additional principles:

- Document parameters, return values, and raised exceptions using Sphinx field lists.
- Include explicit types in docstrings (``:type:`` for parameter types, ``:rtype:`` for return types) to support modules
  without type annotations.

Module docstring template
-------------------------

Every Python module should start with a docstring describing its purpose and contents:

.. code-block:: python

   """
   Brief one-line summary of the module.

   Extended description that explains the module's purpose, key concepts,
   and any important notes about usage. Can be multiple paragraphs.

   Example:
       >>> from mymodule import MyClass
       >>> obj = MyClass()
       >>> obj.my_method()
       42
   """

The module docstring should:

- Start with a one-line summary that fits on a single line
- Leave one blank line after the summary
- Provide an extended description of the module's purpose and contents
- Include example usage if helpful
- Document any important module-level variables or constants
- List any required third-party imports
- Note any important limitations or caveats

For example, this is a good module docstring:

.. code-block:: python

   """
   Utilities for working with vector data in machine learning applications.

   This module provides functions for common vector operations like normalization,
   distance calculations, and similarity metrics. All functions support both
   Python lists and NumPy arrays as input.

   The implementations prioritize numerical stability over performance. For
   high-performance applications, consider using optimized libraries like NumPy
   directly.

   Required dependencies:
       - numpy >= 1.15.0
       - scipy >= 1.3.0

   Example:
       >>> from vectors import normalize, cosine_similarity
       >>> a = [1.0, 2.0, 3.0]
       >>> b = normalize(a)
       >>> cosine_similarity(a, b)
       1.0
   """

Function docstring template
---------------------------

Give a short summary of the function's purpose and its parameters and return values.

For example, this is a good function docstring:

.. code-block:: python

   def normalize_vector(vector, *, eps=1e-12):
       """
       Normalize a 1D numeric vector to unit length.

       :param vector: Input vector.
       :type vector: list[float] | numpy.ndarray
       :param eps: Small constant to avoid division by zero.
       :type eps: float
       :returns: Normalized vector with L2 norm equal to 1.
       :rtype: list[float] | numpy.ndarray
       :raises ValueError: If ``vector`` is empty.

       Example:
           >>> normalize_vector([3.0, 4.0])
           [0.6, 0.8]
       """
       # implementation
       ...

Class docstring template
------------------------

Document public attributes and constructor arguments in the class header:

.. code-block:: python

   class RateLimiter:
       """
       Limit the rate of operations to a maximum number per time window.

       :param int max_calls: Maximum calls allowed per window.
       :param float window_seconds: Window size in seconds.
       :ivar int max_calls: Maximum calls allowed per window.
       :ivar float window_seconds: Window size in seconds.
       :raises ValueError: If ``max_calls`` or ``window_seconds`` is non-positive.

       .. note::
          Instances are thread-safe.
       """

       def __init__(self, max_calls, window_seconds):
           # implementation
           ...

Common sections and fields
--------------------------

- ``:param <name>:`` description of an argument
- ``:type <name>:`` type of an argument, immediate after the parameter name
- ``:returns:`` description of the return value
- ``:rtype:`` return type, immediate after the return value description
- ``:raises <ExcType>:`` when and why an exception is raised
- ``:yields:`` / ``:yield type:`` for generators
- ``:ivar <name>:`` / ``:vartype <name>:`` for instance attributes

Cross‑references and inline markup
----------------------------------

- Reference code objects to create links:
  ``:mod:`package.module``` • ``:class:`package.Class``` • ``:func:`package.func``` • ``:meth:`Class.method``` • ``:attr:`Class.attribute```.
- Use inline literals (text that should be displayed as is) with double backticks, e.g. ``"utf-8"``.
- Try to include links with descriptive text, e.g. ``:ref:`tutorials```.

Admonitions
------------------------

Admonitions are special callout blocks in documentation that highlight important information. 
They're like warning boxes or note boxes (e.g., .. note::, .. warning::) that draw attention to specific points. 

- Use admonitions for emphasis:

  .. code-block:: rst

     .. note::
        This operation is idempotent.

     .. warning::
        Network timeouts should be handled by the caller.

Formatting rules and tips
-------------------------

- Keep lines under ~88 characters for readability.
- Indent continuation lines and blocks consistently within the docstring.
- Leave a blank line before field lists (``:param:``, ``:returns:``, etc.).
- If a function is private or trivial, keep the docstring concise or omit
  section fields.

Quick copy‑paste templates
--------------------------

Function template:

.. code-block:: python

   def your_function(arg1, arg2=None):
       """
       One-line imperative summary.

       Optional extended description spanning multiple lines.

       :param <type> arg1: Description of arg1.
       :param <type> arg2: Description of arg2.
       :returns: What the function returns.
       :rtype: <type>
       :raises SomeError: When something goes wrong.
       """
       ...

Class template:

.. code-block:: python

   class YourClass:
       """
       One-line summary of the class purpose.

       :ivar <type> attr: Description of attribute.
       """

       def __init__(self, param):
           """
           :param <type> param: Description of parameter.
           """
           ...


