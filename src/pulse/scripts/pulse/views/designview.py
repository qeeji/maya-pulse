

from pulse.vendor.Qt import QtWidgets
from .designviews.controls import ControlsPanel
from .designviews.general import GeneralPanel
from .designviews.joints import JointsPanel, JointOrientsPanel
from .designviews.sym import SymmetryPanel
from .designviews.layout import LayoutPanel

__all__ = [
    "DesignViewWidget",
]


class DesignViewWidget(QtWidgets.QWidget):
    """
    A widget containing a collection of panels with tools
    for designing the rig blueprint.
    """

    def __init__(self, parent=None):
        super(DesignViewWidget, self).__init__(parent=parent)

        self.setupUi(self)

    def setupUi(self, parent):
        layout = QtWidgets.QVBoxLayout(parent)

        self.scrollArea = QtWidgets.QScrollArea(parent)
        self.scrollArea.setFrameShape(QtWidgets.QScrollArea.NoFrame)
        self.scrollArea.setWidgetResizable(True)
        layout.addWidget(self.scrollArea)

        self.scrollWidget = QtWidgets.QWidget()
        self.scrollArea.setWidget(self.scrollWidget)

        # scroll layout contains the main layout and a spacer item
        self.scrollLayout = QtWidgets.QVBoxLayout(self.scrollWidget)
        self.scrollLayout.setMargin(0)
        self.scrollLayout.setSpacing(8)

        self.setupPanelsUi(self.scrollLayout, self.scrollWidget)

        spacer = QtWidgets.QSpacerItem(
            20, 20, QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Expanding)
        self.scrollLayout.addItem(spacer)

        self.scrollWidget.setLayout(self.scrollLayout)

    def setupPanelsUi(self, layout, parent):

        controls = ControlsPanel(parent)
        layout.addWidget(controls)

        general = GeneralPanel(parent)
        layout.addWidget(general)

        layoutPanel = LayoutPanel(parent)
        layout.addWidget(layoutPanel)

        joints = JointsPanel(parent)
        layout.addWidget(joints)

        jointOrients = JointOrientsPanel(parent)
        layout.addWidget(jointOrients)

        sym = SymmetryPanel(parent)
        layout.addWidget(sym)

        spacer = QtWidgets.QSpacerItem(
            20, 20, QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Expanding)
        layout.addItem(spacer)
