Version Management and Rollback
=================================

This guide covers how to manage SIC versions in your applications, including checking versions,
rolling back to previous versions, and managing versions on robots.

Checking Your Current Version
------------------------------

To check what version of SIC you currently have installed:

.. code-block:: bash

   pip show social-interaction-cloud

This will display information including the version number:

.. code-block:: text

   Name: social-interaction-cloud
   Version: 1.2.3
   ...

Alternatively, in Python:

.. code-block:: python

   from pkg_resources import get_distribution
   version = get_distribution("social-interaction-cloud").version
   print(f"SIC version: {version}")


Installing a Specific Version
------------------------------

To install a specific version of SIC, use pip with version pinning:

.. code-block:: bash

   # Install a specific version
   pip install social-interaction-cloud==1.2.3

   # Or upgrade/downgrade to a specific version
   pip install --upgrade social-interaction-cloud==1.2.3


Rolling Back to a Previous Version
-----------------------------------

If you need to rollback to a previous version, follow these steps:

**Step 1: Find Available Versions**

Check available versions on PyPI:

.. code-block:: bash

   pip index versions social-interaction-cloud

Or visit https://pypi.org/project/social-interaction-cloud/#history


**Step 2: Uninstall Current Version**

.. code-block:: bash

   pip uninstall social-interaction-cloud


**Step 3: Install Target Version**

.. code-block:: bash

   # Replace 1.2.3 with your desired version
   pip install social-interaction-cloud==1.2.3


**Step 4: Verify Installation**

.. code-block:: bash

   pip show social-interaction-cloud


Managing Versions on Robots (NAO/Pepper)
-----------------------------------------

When you connect to a NAO or Pepper robot, SIC automatically manages version synchronization.

**How It Works:**

1. SIC checks if the framework is installed on the robot
2. Compares the robot's version with your local version
3. If versions don't match, automatically reinstalls on the robot

**NAO Robots:** Install the matching version from PyPI  
**Pepper Robots:** Download from GitHub's ``main`` branch

**Using a Specific Version on NAO:**

NAO robots will automatically match your local version. Simply install the desired version locally:

.. code-block:: bash

   # Install the specific version you want on your local machine
   pip install social-interaction-cloud==1.2.3

.. code-block:: python

   # NAO will automatically install the same version (1.2.3) from PyPI
   from sic_framework.devices import Nao
   
   nao = Nao("10.0.0.100")


Best Practices
--------------

1. **Always use virtual environments** to isolate different project versions
2. **Pin versions** in ``requirements.txt`` for reproducibility
3. **Document which version** you're using in your project README
4. **Test after upgrading** to ensure backward compatibility
5. **Keep local and robot versions in sync** to avoid unexpected behavior

.. warning::
   Rolling back to very old versions may cause compatibility issues with newer
   Python versions or operating systems. Always test thoroughly after version changes.

