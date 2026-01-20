"""
Show/Hide Each Element Panel Plugin for QGIS
"""

def classFactory(iface):
    """Load FeatureVisibilityToggle class from file feature_visibility_toggle.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .feature_visibility_toggle import FeatureVisibilityToggle
    return FeatureVisibilityToggle(iface)
