import sys
from lxml import etree

print("%-20s: %s" % ('Python', sys.version_info))
print("%-20s: %s" % ('lxml.etree', etree.LXML_VERSION))
print("%-20s: %s" % ('libxml used', etree.LIBXML_VERSION))
print("%-20s: %s" % ('libxml compiled', etree.LIBXML_COMPILED_VERSION))
print("%-20s: %s" % ('libxslt used', etree.LIBXSLT_VERSION))
print("%-20s: %s" % ('libxslt compiled', etree.LIBXSLT_COMPILED_VERSION))