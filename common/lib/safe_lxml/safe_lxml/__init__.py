"""
Defuse vulnerabilities in XML packages.
"""


def defuse_xml_libs():
    """
    Monkey patch and defuse all stdlib xml packages and lxml.
    """
    from defusedxml import defuse_stdlib
    defuse_stdlib()

    import lxml
    import lxml.etree
    from . import etree as safe_etree

<<<<<<< HEAD
    lxml.etree = safe_etree
=======
    lxml.etree = safe_etree
>>>>>>> fa0bd35cc1c2ef00890f1bba3b8be2eeb72422b4
