Using miniconda
===============

The easiest way to work with Python is through
`miniconda <https://conda.io/miniconda.html>`__, which helps you create
virtual environments isolated of each other and local to your UNIX user.
This way you can switch between Python and packages versions.

Installing conda
----------------

Download the appropriate installer from
`here <https://conda.io/miniconda.html>`__.

Example using 64-bit Linux:

.. code:: shell

    # dowload installer
    curl https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -o miniconda.sh

    # run it
    bash miniconda.sh

    # follow instructions...

Using conda
-----------

Create a new environment for your project with this command:

.. code:: shell

    conda create --name=project

You can specify a Python version:

.. code:: shell

    conda create --name=project python=3.5

Activate your environment:

.. code:: shell

    source activate project

Install packages in that environment:

.. code:: shell

    pip install numpy

Deactivate environment:

.. code:: shell

    source deactivate

Other resources
---------------

-  `miniconda cheat
   sheet <https://conda.io/docs/_downloads/conda-cheatsheet.pdf>`__
