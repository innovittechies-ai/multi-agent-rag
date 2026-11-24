"""PythonAnywhere entry point.

On the Web tab, the WSGI file should import this object:

    import sys
    sys.path.insert(0, "/home/YOUR_USERNAME/rag-arch/backend")
    from wsgi import application
"""

from app import app as application
