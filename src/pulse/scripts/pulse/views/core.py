
import logging
import maya.cmds as cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
import pymetanode as meta

import pulse
from pulse.vendor.Qt import QtCore, QtWidgets, QtGui
from pulse.core import BlueprintLifecycleEvents, BlueprintChangeEvents

__all__ = [
    'BlueprintUIModel',
    'BuildItemSelectionModel',
    'BuildItemTreeModel',
    'buttonCommand',
    'CollapsibleFrame',
    'PulseWindow',
    # 'BuildItemModelItem',
]

LOG = logging.getLogger(__name__)


def buttonCommand(func, *args, **kwargs):
    """
    Return a function that can be called which will execute
    the given function with proper undo chunk handling.
    """

    def wrapper():
        cmds.undoInfo(openChunk=True)
        try:
            func(*args, **kwargs)
        except Exception as e:
            cmds.error(e)
        finally:
            cmds.undoInfo(closeChunk=True)

    return wrapper


class CollapsibleFrame(QtWidgets.QFrame):
    """
    A QFrame that can be collapsed when clicked.
    """

    collapsedChanged = QtCore.Signal(bool)

    def __init__(self, parent):
        super(CollapsibleFrame, self).__init__(parent)
        self._isCollapsed = False

    def mouseReleaseEvent(self, QMouseEvent):
        if QMouseEvent.button() == QtCore.Qt.MouseButton.LeftButton:
            self.setIsCollapsed(not self._isCollapsed)
        else:
            return super(CollapsibleFrame, self).mouseReleaseEvent(QMouseEvent)

    def setIsCollapsed(self, newCollapsed):
        """
        Set the collapsed state of this frame.
        """
        self._isCollapsed = newCollapsed
        self.collapsedChanged.emit(self._isCollapsed)

    def isCollapsed(self):
        """
        Return True if the frame is currently collapsed.
        """
        return self._isCollapsed


class PulseWindow(MayaQWidgetDockableMixin, QtWidgets.QMainWindow):
    """
    A base class for any standalone window in the Pulse UI. Integrates
    the Maya builtin dockable mixin, and prevents multiple instances
    of the window.
    """

    OBJECT_NAME = None

    @classmethod
    def createAndShow(cls):
        cls.deleteInstances()
        window = cls()
        window.show()
        return window

    @classmethod
    def exists(cls):
        """
        Return True if an instance of this window exists
        """
        result = False
        if cmds.workspaceControl(cls.getWorkspaceControlName(), q=True, ex=True):
            result = True
        if cmds.workspaceControl(cls.getWorkspaceControlName(), q=True, ex=True):
            result = True
        if cmds.window(cls.OBJECT_NAME, q=True, ex=True):
            result = True
        return result

    @classmethod
    def deleteInstances(cls):
        """
        Delete existing instances of this window
        """
        result = False
        # close and delete an existing workspace control
        if cmds.workspaceControl(cls.getWorkspaceControlName(), q=True, ex=True):
            cmds.workspaceControl(cls.getWorkspaceControlName(), e=True, close=True)
            result = True
        if cmds.workspaceControl(cls.getWorkspaceControlName(), q=True, ex=True):
            cmds.deleteUI(cls.getWorkspaceControlName(), control=True)
            result = True
        if cmds.window(cls.OBJECT_NAME, q=True, ex=True):
            cmds.deleteUI(cls.OBJECT_NAME, window=True)
            result = True
        return result

    @classmethod
    def getWorkspaceControlName(cls):
        return cls.OBJECT_NAME + 'WorkspaceControl'

    def __init__(self, parent=None):
        super(PulseWindow, self).__init__(parent=parent)
        self.setObjectName(self.OBJECT_NAME)
        self.setProperty('saveWindowPref', True)

    def show(self):
        """
        Show the PulseWindow.
        """
        super(PulseWindow, self).show(dockable=True, retain=False)




class BlueprintUIModel(QtCore.QObject):
    """
    The owner and manager of various models representing a Blueprint
    in the scene. All reading and writing for the Blueprint through
    the UI should be done using this model.

    BlueprintUIModels can exist without the Blueprint node in the
    scene. In this case the model won't be functional, but will
    automatically update if the same named Blueprint node is created.

    The model maintains a list of subscribers used to properly manage
    and cleanup Maya callbacks, so any QWidgets should call addSubscriber
    and removeSubscriber on the model during show and hide events (or similar).
    """

    # shared instances, mapped by blueprint node name
    INSTANCES = {}

    @classmethod
    def getDefaultModel(cls):
        return cls.getSharedModel(pulse.BLUEPRINT_NODENAME)

    @classmethod
    def getSharedModel(cls, blueprintNodeName):
        """
        Return a shared model for a specific Blueprint node,
        creating a new model if necessary. Will always return
        a valid BlueprintUIModel.
        """
        if blueprintNodeName not in cls.INSTANCES:
            cls.INSTANCES[blueprintNodeName] = cls(blueprintNodeName)
        return cls.INSTANCES[blueprintNodeName]

    @classmethod
    def deleteSharedModel(cls, blueprintNodeName):
        if blueprintNodeName in cls.INSTANCES:
            del cls.INSTANCES[blueprintNodeName]

    # the blueprint node was created
    blueprintCreated = QtCore.Signal()

    # the blueprint node was deleted
    blueprintDeleted = QtCore.Signal()

    # the blueprint node was modified from loading
    blueprintNodeChanged = QtCore.Signal()

    # a config property on the blueprint changed
    blueprintPropertyChanged = QtCore.Signal(str)


    def __init__(self, blueprintNodeName, parent=None):
        super(BlueprintUIModel, self).__init__(parent=parent)

        # the blueprint node this model is associated with
        self.blueprintNodeName = blueprintNodeName

        # the blueprint of this model
        self.blueprint = None
        if cmds.objExists(self.blueprintNodeName):
            # load from existing node
            self.blueprint = pulse.Blueprint.fromNode(self.blueprintNodeName)

        # the tree item model and selection model for BuildItems
        self.buildItemTreeModel = BuildItemTreeModel(self.blueprint)
        self.buildItemTreeModel.dataChanged.connect(self._onItemModelChanged)
        self.buildItemSelectionModel = BuildItemSelectionModel(self.buildItemTreeModel)

        self._modelSubscribers = []

        self._isSaving = False

        lifeEvents = BlueprintLifecycleEvents.getShared()
        lifeEvents.onBlueprintCreated.appendUnique(self._onBlueprintCreated)
        lifeEvents.onBlueprintDeleted.appendUnique(self._onBlueprintDeleted)

    def __del__(self):
        super(BlueprintUIModel, self).__del__()
        lifeEvents = BlueprintLifecycleEvents.getShared()
        lifeEvents.onBlueprintCreated.removeAll(self._onBlueprintCreated)
        lifeEvents.onBlueprintDeleted.removeAll(self._onBlueprintDeleted)

    def _subscribeToBlueprintNodeChanges(self):
        changeEvents = BlueprintChangeEvents.getShared(self.blueprintNodeName)
        if changeEvents:
            changeEvents.onBlueprintNodeChanged.appendUnique(self._onBlueprintNodeChanged)
            changeEvents.addSubscriber(self)
            LOG.debug('subscribed to blueprint node changes')

    def _setBlueprint(self, newBlueprint):
        self.blueprint = newBlueprint
        self.buildItemTreeModel.setBlueprint(self.blueprint)
        self.rigNameChanged.emit(self.getRigName())

    def addSubscriber(self, subscriber):
        """
        Add a subscriber to this model. Will enable Maya callbacks
        if this is the first subscriber.
        """
        if subscriber not in self._modelSubscribers:
            self._modelSubscribers.append(subscriber)
        # if any subscribers, subscribe to maya callbacks
        if self._modelSubscribers:
            lifeEvents = BlueprintLifecycleEvents.getShared()
            lifeEvents.addSubscriber(self)
            changeEvents = BlueprintChangeEvents.getShared(self.blueprintNodeName)
            if changeEvents:
                changeEvents.addSubscriber(self)

        # we may have missed events since last subscribed,
        # so make sure blueprint exists == node exists
        if cmds.objExists(self.blueprintNodeName):
            if self.blueprint is None:
                self._setBlueprint(pulse.Blueprint.fromNode(self.blueprintNodeName))
        else:
            if self.blueprint is not None:
                self._setBlueprint(None)

    def removeSubscriber(self, subscriber):
        """
        Remove a subscriber from this model. Will disable
        Maya callbacks if no subscribers remain.
        """
        if subscriber in self._modelSubscribers:
            self._modelSubscribers.remove(subscriber)
        # if no subscribers, unsubscribe from maya callbacks
        if not self._modelSubscribers:
            lifeEvents = BlueprintLifecycleEvents.getShared()
            lifeEvents.removeSubscriber(self)
            changeEvents = BlueprintChangeEvents.getShared(self.blueprintNodeName)
            if changeEvents:
                changeEvents.removeSubscriber(self)

    def _onBlueprintCreated(self, node):
        if node.nodeName() == self.blueprintNodeName:
            self._setBlueprint(pulse.Blueprint.fromNode(self.blueprintNodeName))
            self._subscribeToBlueprintNodeChanges()
            self.blueprintCreated.emit()

    def _onBlueprintDeleted(self, node):
        if node.nodeName() == self.blueprintNodeName:
            self._setBlueprint(None)
            # doing some cleanup since we can here
            BlueprintChangeEvents.cleanupSharedInstances()
            self.blueprintDeleted.emit()

    def _onBlueprintNodeChanged(self, node):
        """
        The blueprint node has changed, reload its data
        """
        if not self._isSaving:
            selectedPaths = self.buildItemSelectionModel.getSelectedItemPaths()
            self.load()
            self.blueprintNodeChanged.emit()
            self.buildItemSelectionModel.setSelectedItemPaths(selectedPaths)

    def _onItemModelChanged(self):
        self.save()

    def isReadOnly(self):
        """
        Return True if the Blueprint is not able to be modified.
        This will be True if the Blueprint doesn't exist.
        """
        return self.blueprint is None

    def getBlueprint(self):
        """
        Return the Blueprint represented by this model.
        """
        return self.blueprint

    def getRigName(self):
        # TODO: better solve for blueprint meta data
        if self.blueprint:
            return self.blueprint.rigName

    def setRigName(self, newRigName):
        if not self.isReadOnly():
            self.blueprint.rigName = newRigName
            self.rigNameChanged.emit(self.blueprint.rigName)
            self.save()

    def save(self):
        """
        Save the Blueprint data to the blueprint node
        """
        self._isSaving = True
        # TODO: save after the deferred call instead of on every call?
        self.blueprint.saveToNode(self.blueprintNodeName)
        cmds.evalDeferred(self._saveFinishedDeferred)

    def _saveFinishedDeferred(self):
        self._isSaving = False
        # TODO: fire a signal

    def load(self):
        """
        Load the Blueprint data from the blueprint node
        """
        LOG.debug('loading...')
        # TODO: preserve selection by item path
        if (cmds.objExists(self.blueprintNodeName) and
                pulse.Blueprint.isBlueprintNode(self.blueprintNodeName)):
            # node exists and is a valid blueprint
            if self.blueprint is None:
                self._setBlueprint(pulse.Blueprint.fromNode(self.blueprintNodeName))
            else:
                self.blueprint.loadFromNode(self.blueprintNodeName)
                self.buildItemTreeModel.modelReset.emit()
            # attempt to preserve selection
            LOG.debug('load finished.')

        else:
            # attempted to load from non-existent or invalid node
            self._setBlueprint(None)
            LOG.debug('load failed.')

    def createNode(self):
        """
        Delete the blueprint node of this model
        """
        if not cmds.objExists(self.blueprintNodeName):
            pulse.Blueprint.createNode(self.blueprintNodeName)

    def deleteNode(self):
        """
        Delete the blueprint node of this model
        """
        if cmds.objExists(self.blueprintNodeName):
            cmds.delete(self.blueprintNodeName)



# class BuildItemModelItem(object):
#     """
#     A Qt-friendly wrapper for BuildItems that allows them
#     to be more easily used in a Qt tree model.
#     """

#     def __init__(self, buildItem):
#         if not isinstance(buildItem, pulse.BuildItem):
#             raise ValueError("Expected BuildItem, got {0}".format(
#                 type(buildItem).__name__))
#         self._buildItem = buildItem

#     def children(self):
#         """
#         Return the children of this BuildItem as a list of BuildItemModelItems
#         """
#         return [BuildItemModelItem(c) for c in self._buildItem.itemChildren]

#     def columnCount(self):
#         """
#         Return how many columns of data this BuildItem has
#         """
#         return 1

#     def childCount(self):
#         """
#         Return how many children this BuildItem has
#         """
#         return len(self._buildItem.itemChildren)

#     def child(self, row):
#         """
#         Return the child of this BuildItem at the given row (index).
#         Returns a BuildItemModelItem instance.
#         """
#         return self.children()[row]

#     def parent(self):
#         """
#         Return the parent of this BuildItem, as a BuildItemModelItem
#         """
#         if self._buildItem.itemParent:
#             return BuildItemModelItem(self._buildItem.itemParent)

#     def row(self):
#         """
#         Return the row index of this item.
#         """
#         if self._buildItem.itemParent:
#             return self._buildItem.itemParent.itemChildren.index(self._buildItem)
#         return 0

#     def insertChildren(self, position, childBuildItems):
#         """
#         Insert an array of children into this item starting
#         at a specified position.
#         """
#         if not self._buildItem.itemCanHaveChildren:
#             return False

#         if position < 0:
#             position = self.childCount()

#         for childBuildItem in childBuildItems:
#             self._buildItem.insertChild(position, childBuildItem)

#         return True

#     def removeChildren(self, position, count):
#         """
#         Remove one or more children from thie item starting
#         at a specified position.
#         """
#         if not self._buildItem.itemCanHaveChildren:
#             return False

#         if position < 0 or position + count > self.childCount():
#             return False

#         for _ in range(count):
#             self._buildItem.removeChildAt(position)

#         return True

#     def setData(self, column, value):
#         """
#         Set data for this build item. Only supports setting
#         the name of BuildItems.
#         """
#         if value:
#             self._buildItem.setName(value)
#         else:
#             self._buildItem.setName(self._buildItem.getDefaultName())

#         return True


#     def data(self, column, role=QtCore.Qt.DisplayRole):
#         """
#         Return data for this item, for a specific Qt display role.
#         """
#         if role == QtCore.Qt.DisplayRole:
#             return self._buildItem.getDisplayName()

#         elif role == QtCore.Qt.EditRole:
#             return self._buildItem.itemName

#         elif role == QtCore.Qt.DecorationRole:
#             iconFile = self._buildItem.getIconFile()
#             if iconFile:
#                 return QtGui.QIcon(iconFile)

#         elif role == QtCore.Qt.SizeHintRole:
#             return QtCore.QSize(0, 20)

#         elif role == QtCore.Qt.ForegroundRole:
#             color = self._buildItem.getColor()
#             if color:
#                 return QtGui.QColor(*[c * 255 for c in color])

#     def isDropEnabled(self):
#         return self._buildItem.itemCanHaveChildren




class BuildItemTreeModel(QtCore.QAbstractItemModel):
    """
    A Qt tree model for viewing and modifying the BuildItem
    hierarchy of a Blueprint.
    """

    def __init__(self, blueprint=None, parent=None):
        super(BuildItemTreeModel, self).__init__(parent=parent)
        self._blueprint = blueprint

    def setBlueprint(self, newBlueprint):
        """
        Set a new Blueprint for this model, causing a full full model reset.
        """
        if self._blueprint is not newBlueprint:
            self._blueprint = newBlueprint
            self.modelReset.emit()

    def item(self, row, column, parent=QtCore.QModelIndex()):
        """
        Return the BuildItem for a row, column, and parent index.
        """
        return self.itemForIndex(self.index(row, column, parent))

    def itemForIndex(self, index):
        """
        Return the BuildItem of a QModelIndex.
        """
        if index.isValid():
            return index.internalPointer()
        else:
            return self.blueprint.rootItem

    def index(self, row, column, parent=QtCore.QModelIndex()): # override
        """
        Create a QModelIndex for a row, column, and parent index
        """
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()

        childItem = self.itemForIndex(parent).child(row)
        if childItem:
            return self.createIndex(row, column, childItem.buildItem)
        else:
            return QtCore.QModelIndex()

    # def indexForItem(self, buildItem):
    #     """
    #     Create a QModelIndex for a BuildItem in the blueprint
    #     """
    #     # the list of items from top-most parent downward
    #     # that makes the parent hierarchy of the item
    #     itemHierarchy = [buildItem]
    #     thisItem = buildItem
    #     while thisItem.itemParent:
    #         itemHierarchy.insert(0, thisItem.itemParent)
    #         thisItem = thisItem.itemParent

    #     thisIndex = QtCore.QModelIndex()
    #     for item in itemHierarchy[1:]:
    #         row = BuildItemModelItem(item).row()
    #         thisIndex = self.index(row, 0, thisIndex)

    #     return thisIndex

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsDropEnabled

        flags = QtCore.Qt.ItemIsEnabled \
            | QtCore.Qt.ItemIsSelectable \
            | QtCore.Qt.ItemIsDragEnabled \
            | QtCore.Qt.ItemIsEditable

        if self.itemForIndex(index).itemCanHaveChildren:
            flags |= QtCore.Qt.ItemIsDropEnabled

        return flags

    def supportedDropActions(self):
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    def columnCount(self, parent=QtCore.QModelIndex()): # override
        return self.itemForIndex(parent).columnCount()

    def rowCount(self, parent=QtCore.QModelIndex()): # override
        return self.itemForIndex(parent).childCount()

    def parent(self, index): # override
        if not index.isValid():
            return QtCore.QModelIndex()

        parentItem = self.itemForIndex(index).parent()
        if (not parentItem) or (parentItem.buildItem == self.blueprint.rootItem):
            return QtCore.QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem.buildItem)

    def insertRows(self, position, rows, parent=QtCore.QModelIndex()):
        raise RuntimeError("Cannot insert rows without data, use insertBuildItems instead")

    def insertBuildItems(self, position, childBuildItems, parent=QtCore.QModelIndex()):
        self.beginInsertRows(parent, position, position + len(childBuildItems) - 1)
        success = self.itemForIndex(parent).insertChildren(position, childBuildItems)
        self.endInsertRows()
        return success

    def removeRows(self, position, rows, parent=QtCore.QModelIndex()):
        self.beginRemoveRows(parent, position, position + rows - 1)
        success = self.itemForIndex(parent).removeChildren(position, rows)
        self.endRemoveRows()
        return success

    def data(self, index, role=QtCore.Qt.DisplayRole): # override
        # QtCore.Qt.ForegroundRole
        if index.isValid():
            return self.itemForIndex(index).data(index.column(), role)

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid():
            return False

        if role != QtCore.Qt.EditRole:
            return False

        result = self.itemForIndex(index).setData(index.column(), value)

        if result:
            self.dataChanged.emit(index, index, [])

        return result

    def mimeTypes(self):
        return ['text/plain']

    def mimeData(self, indexes):
        result = QtCore.QMimeData()
        # TODO: this is wrong because serialization will include
        #       children and we don't want that here
        itemDataList = [self.itemForIndex(index).buildItem.serialize() for index in indexes]
        datastr = meta.encodeMetaData(itemDataList)
        result.setData('text/plain', datastr)
        return result

    def dropMimeData(self, data, action, row, column, parent):
        try:
            itemDataList = meta.decodeMetaData(str(data.data('text/plain')))
        except Exception as e:
            print(e)
            return False
        else:
            newBuildItems = [pulse.BuildItem.create(itemData) for itemData in itemDataList]
            return self.insertBuildItems(row, newBuildItems, parent)



class BuildItemSelectionModel(QtCore.QItemSelectionModel):
    """
    The selection model for the BuildItems of a Blueprint. Allows
    a singular selection that is shared across all UI for the Blueprint.
    An instance of this model should be acquired by going through
    the BlueprintUIModel for a specific Blueprint.
    """

    def getSelectedItems(self):
        """
        Return the currently selected BuildItems
        """
        indexes = self.selectedIndexes()
        items = []
        for index in indexes:
            if index.isValid():
                buildItem = index.internalPointer()
                if buildItem:
                    items.append(buildItem)
        return list(set(items))

    def getSelectedGroups(self):
        """
        Return indexes of the selected BuildItems that can have children
        """
        indexes = self.selectedIndexes()
        indeces = []
        for index in indexes:
            if index.isValid():
                buildItem = index.internalPointer()
                if buildItem and buildItem.itemCanHaveChildren:
                    indeces.append(index)
                # TODO: get parent until we have an item that supports children
        return list(set(indeces))

    def getSelectedAction(self):
        """
        Return the currently selected BuildAction, if any.
        """
        items = self.getSelectedItems()
        return [i for i in items if isinstance(i, pulse.BuildAction)]

    def getSelectedItemPaths(self):
        """
        Return the full paths of the selected BuildItems
        """
        items = self.getSelectedItems()
        return [i.getFullPath() for i in items]

    def setSelectedItemPaths(self, paths):
        """
        Set the selection using BuildItem paths
        """
        model = self.model()
        if not model or not hasattr(model, 'blueprint'):
            return

        # blueprint = model.blueprint
        # items = [blueprint.getItemByPath(p) for p in paths]
        # indeces = [model.indexForItem(i) for i in items if i]
        # self.clear()
        # for index in indeces:
        #     if index.isValid():
        #         self.select(index, QtCore.QItemSelectionModel.Select)
