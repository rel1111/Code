from distutils.core import setup
import py2exe

setup(
    console=['production_plan.py'],   # or use 'windows=['production_plan.py']' if you don’t want a console window
    options={
        'py2exe': {
            'includes': ['pandas', 'matplotlib', 'tkinter', 'openpyxl'],
            'bundle_files': 1,  # bundle everything into a single exe
            'compressed': True
        }
    },
    zipfile=None
)
