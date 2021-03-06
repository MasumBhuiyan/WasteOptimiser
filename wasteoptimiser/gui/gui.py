from PyQt5.uic import loadUiType
from PyQt5 import QtCore, QtGui, QtWidgets

from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)

import os
import time
Ui_MainWindow, QMainWindow = loadUiType(os.path.join(os.path.dirname(__file__), '../resources/WasteOptimiserGUI.ui'))

from wasteoptimiser.optimiser.localsearch import LocalSearch #TODO: REMOVE

def clamp(val, minv, maxv):
    if val is not None: return min(maxv, max(val, minv))
    else: return 0

class InputControl():
    def __init__(self, name, spinbox, checkbox):
        self.name = name
        self.spinbox = spinbox
        self.checkbox = checkbox

    def getName(self):
        return self.name

    def getCount(self):
        return self.spinbox.value()

    def setCount(self, val):
        self.spinbox.setValue(val)

    def getConvex(self):
        return self.checkbox.isChecked()

    def setConvex(self, val):
        self.checkbox.setChecked(val)

    def reset(self):
        self.setCount(0)
        self.setConvex(True)


class MyGroupBox(QtWidgets.QGroupBox):
    """Ectending functionality of QGroupBox - hover and click events"""
    
    name = "nothing"
    click_callback = print

    style_QGroupBox_normal = """
    """

    style_QGroupBox_hover = """
        background-color: #ddd;
    """

    style_QGroupBox_click = """
        background-color: #ccc;
    """

    def event(self, e):
        #print(e.type())
        t = e.type()
        if t == QtCore.QEvent.HoverEnter: # mouse enter
            self.setStyleSheet(self.style_QGroupBox_hover)
        elif t == QtCore.QEvent.HoverLeave: # mouse leave
            self.setStyleSheet(self.style_QGroupBox_normal)
        elif t == QtCore.QEvent.MouseButtonPress: # mouse click
            self.setStyleSheet(self.style_QGroupBox_click)
        elif t == QtCore.QEvent.MouseButtonRelease: # mouse release
            self.setStyleSheet(self.style_QGroupBox_hover)
            self.click_callback(self.info)
        super(MyGroupBox, self).event(e)
        return True


class OptimiserThread(QtCore.QThread):
    def __init__(self, function):
        QtCore.QThread.__init__(self)
        self.func = function
    
    def run(self):
        self.func()

class Mode():
    none = 0
    drawing = 1
    subtracting = 2
    deleting = 3
    

class MainWindow(Ui_MainWindow, QMainWindow):
    def __init__(self, api):
        super(MainWindow, self).__init__()
        self.setupUi(self)
        self.setWindowTitle('Waste Optimiser')
        self.api = api
        self.mode = Mode.none
        self.drawn_shape = []
        self.first_point = ()
        self.last_point = ()
        self.close_to_last = False
        self.drawn_shape_handle = None
        self.info_message = ""
        self.hole_to_remove = None
        self.input_list = []

    ## FUNCTIONS ##
    def openFolder(self, folder):
        """Displays files from the given folder in list"""
        if not folder: return
        self.api.settings.input_path = folder
        self.api.constructShapeList(self.api.settings.input_path)
        items = self.api.shape_dict.keys()
        self.lb_input_path.setText('...' + folder[-30:])
        self.clearInputList()
        self.fillInputList(items)

    ## CALLBACKS ##
    def askFolder(self):
        """Opens a select folder dialog and then displays files from that folder"""

        folder = QtWidgets.QFileDialog.getExistingDirectory(self,"Select folder", '../../')
        self.openFolder(folder)
    
    def selectAndDrawShape(self, name):
        """Sets the clicked shape as selected and draws it to the preview figure"""

        self.figure_preview.clear()
        self.lb_preview_info.setText("Loading...")
        shapes = self.api.shape_dict[name]['shape']

        if not shapes:
            self.api.selected_shape_name = None
            self.lb_preview_info.setText("Invalid gcode file")
        else:
            self.api.selected_shape_name = name

            first_shape = [shapes[-1]]
            next_shapes = shapes[:-1]

            self.figure_preview.drawShapes(first_shape, 'r-', fill="#f6929c")
            self.figure_preview.drawShapes(next_shapes, 'r-', fill="#ffffff")

            self.figure_preview.draw([[0, 0]], 'r+')
            dimensions = self.api.getShapeDimensions()
            self.lb_preview_info.setText("Dimensions: " + str(round(dimensions[0],3)) + " x " + str(round(dimensions[1], 3)) + " mm")
        self.canvasPreview.draw()

    def applySettings(self):
        """Applies settings to the optimiser module"""

        self.api.optimiser.setBoardSize((self.sb_settings_width.value(), self.sb_settings_height.value()))
        self.api.optimiser.hole_offset = self.sb_settings_hole_offset.value()
        self.api.optimiser.edge_offset = self.sb_settings_edge_offset.value()
        self.api.optimiser.preffered_pos = self.cb_settings_location.currentIndex()
        self.api.optimiser.small_first = self.cb_settings_small_first.isChecked()
        self.drawWorkspace()

    def updateSettingsGUI(self):
        self.sb_settings_width.setValue(self.api.optimiser.width)
        self.sb_settings_height.setValue(self.api.optimiser.height)
        self.sb_settings_edge_offset.setValue(self.api.optimiser.edge_offset)
        self.sb_settings_hole_offset.setValue(self.api.optimiser.hole_offset)
        self.cb_settings_location.setCurrentIndex(self.api.optimiser.preffered_pos)

    def drawShapeInWorkspace(self): #TODO: Delete
        if not self.api.selected_shape_name: return
        self.figure_workspace.drawShapes(self.api.getSelectedShape())
        self.canvasWorkspace.draw()


    def drawWorkspace(self):
        """Draws everything into workspace"""

        self.figure_workspace.clear()
        self.figure_workspace.draw(self.api.optimiser.getBoardShape())
        holes = self.api.optimiser.getHoles('holes')
        if holes:
            self.figure_workspace.drawShapes(holes, options='k--', fill="#aaaaaa")
        holes = self.api.optimiser.getHoles('shapes')
        if holes:
            self.figure_workspace.drawShapes(holes, options='r-', fill="#f6929c")
        self.canvasWorkspace.draw()

    def startOptimisation(self):
        """Sets shape in the optimiser to the currently selected shape"""

        self.api.stop_flag = False
        print("optimisation started")
        self.optimiserThread = OptimiserThread(self.api.placeAllSelectedShapes)
        self.optimiserThread.finished.connect(self.optimisationEnded)
        self.progress_bar_optimisation.setMaximum(self.api.getAllShapesCount())
        self.progress_bar_optimisation.setValue(0)

        self.pb_optimiser_start.setVisible(False)
        self.progress_bar_optimisation.setVisible(True)

        self.progressBarUpdateTimer = QtCore.QTimer()
        self.progressBarUpdateTimer.timeout.connect(self.updateOptimisationProgressBar)
        self.progressBarUpdateTimer.start(100)

        self.workspaceUpdateTimer = QtCore.QTimer()
        self.workspaceUpdateTimer.timeout.connect(self.drawWorkspace)
        self.workspaceUpdateTimer.start(2000)

        self.optimiserThread.start()

    def debug_placeOneShape(self):
        print("printing ", self.api.selected_shape_name)
        self.api.optimiser.setShape(self.api.getSelectedShape()[-1])
        self.api.optimiser.initStartpoly()
        self.figure_workspace.drawShapes(self.api.optimiser.getStartpoly(), '+:r')
        self.canvasWorkspace.draw()
        

    def optimisationEnded(self):
        self.optimiserThread.exit()
        self.progress_bar_optimisation.setVisible(False)
        self.pb_optimiser_start.setVisible(True)
        self.progressBarUpdateTimer.stop()
        self.workspaceUpdateTimer.stop()
        print("optimisation finished")
        self.drawWorkspace()
        self.canvasWorkspace.draw()

    
    def updateOptimisationProgressBar(self):
        self.progress_bar_optimisation.setValue(self.api.num_placed_shapes)


    def clearWorkspace(self):
        self.api.optimiser.__init__(self.api.logger)
        self.applySettings()

    def clearShapes(self):
        self.api.optimiser.hole_shapes.clear()
        self.drawWorkspace()

    def startDrawing(self):
        self.info_message = 'Click to add a point, click near the first point to finish shape. Right click to cancel.'
        self.lb_workspace_info.setText(self.info_message)
        self.mode = Mode.drawing
        self.drawn_shape = []
        self.last_point = ()
        self.first_point = ()
        self.close_to_last = False

    def stopDrawing(self):
        self.info_message = ''
        self.lb_workspace_info.setText(self.info_message)
        self.mode = Mode.none
        self.figure_workspace.remove('last')
        self.figure_workspace.remove('temp')
        self.figure_workspace.remove('new_shape')
        self.figure_workspace.remove('first_point')
        self.drawWorkspace()

    def startSubtracting(self):
        self.startDrawing()
        self.mode = Mode.subtracting

    def startDeleting(self):
        self.info_message = 'Click on a hole you want to delete. Right click to cancel.'
        self.lb_workspace_info.setText(self.info_message)
        self.mode = Mode.deleting

    def stopDeleting(self):
        self.info_message = ''
        self.lb_workspace_info.setText(self.info_message)
        self.mode = Mode.none
        self.drawWorkspace()

    def cancelShape(self):
        self.stopDrawing()
        self.canvasWorkspace.draw()

    def finishShape(self):
        self.drawn_shape.append(self.first_point)
        self.api.optimiser.addHole(self.drawn_shape)
        self.stopDrawing()
        self.startDrawing()

    def subtractShape(self):
        self.drawn_shape.append(self.first_point)
        self.api.optimiser.subtractHole(self.drawn_shape)
        self.stopDrawing()
        self.startDrawing()
        self.mode = Mode.subtracting
        

    def workspaceExport(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self,"Where to save current worksapce...", "Workspace.json", "JSON files (*.json);;All Files (*)")
        if not filename:
            return
        self.api.saveWorkspace(filename)

    def workspaceImport(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self,"Select workspace file to load", "", "JSON files (*.json);;All Files (*)")
        if not filename:
            return
        self.api.loadWorkspace(filename)
        self.updateSettingsGUI()
        self.drawWorkspace()

    def workspaceMouseMotion(self, event):
        x = clamp(event.xdata, 0, self.api.optimiser.width)
        y = clamp(event.ydata, 0, self.api.optimiser.height)
        self.lb_workspace_info.setText(self.info_message + ' [' + str(round(x, 2)) + ', ' + str(round(y, 2)) + ']')

        if self.mode == Mode.drawing or self.mode == Mode.subtracting:
            pointopt = 'k+'
            lineopt = 'k--'
            if self.mode == Mode.subtracting: pointopt = 'r+';lineopt = 'r--'
            self.figure_workspace.remove('temp')
            if not self.first_point:
                self.figure_workspace.draw((x, y), options=pointopt, gid = 'temp')
            else:
                self.figure_workspace.draw((self.last_point, (x, y)), options=lineopt, gid = 'temp')
                self.figure_workspace.remove('last')
                if abs(x-self.first_point[0])<50 and abs(y-self.first_point[1])<50 and len(self.drawn_shape) > 2:
                    self.close_to_last = True
                    self.figure_workspace.draw((x, y), options='ro', gid = 'last')
                else:
                    self.close_to_last = False
            self.canvasWorkspace.draw()

        elif self.mode == Mode.deleting:
            self.figure_workspace.remove('temp')
            self.figure_workspace.draw((x, y), options='rX', gid = 'temp')
            self.hole_to_remove = self.api.optimiser.queryHole((x, y))
            if self.hole_to_remove:
                self.figure_workspace.draw(self.hole_to_remove.boundary.coords, options='r-', gid='temp')
            self.canvasWorkspace.draw()


    def workspaceMouseClicked(self, event):
        x = clamp(event.xdata, 0, self.api.optimiser.width)
        y = clamp(event.ydata, 0, self.api.optimiser.height)
        if self.mode == Mode.drawing or self.mode == Mode.subtracting:
            shapeopt = 'k-'
            lineopt = 'k--'
            if self.mode == Mode.subtracting: shapeopt = 'r-'; lineopt = 'r--'
            if event.button == 1: # left mouse button
                self.figure_workspace.remove('new_shape')
                if not self.first_point:
                    self.first_point = (x, y)
                    self.figure_workspace.draw(self.first_point, 'ro', gid='first_point')
                if self.close_to_last:
                    if self.mode == Mode.subtracting:
                        self.subtractShape()
                    else:
                        self.finishShape()
                    return
                else:
                    self.last_point = (x, y)
                    self.drawn_shape.append(self.last_point)
                    self.figure_workspace.draw(self.drawn_shape, options=shapeopt, gid = 'new_shape')
                    self.canvasWorkspace.draw()
            elif event.button == 3: # right mouse button
                self.cancelShape()
        elif self.mode == Mode.deleting:
            if event.button == 1: # left mouse button
                if self.hole_to_remove: self.api.optimiser.removeHole(self.hole_to_remove)
                self.stopDeleting()
                self.startDeleting()
            elif event.button == 3: # right mouse button
                self.stopDeleting()
            
        #TODO: DELETE
        elif event.button == 2:
            self.api.optimiser.position = (x, y)
            g_search = LocalSearch(self.api.optimiser.shape,
                self.api.optimiser.position,
                self.api.optimiser.angle,
                self.api.optimiser.circle_radius,
                self.api.optimiser.holes)
            print(g_search.getFitness())
            print()
            self.drawWorkspace()
            self.figure_workspace.draw(self.api.optimiser.getShapeOriented())
            self.figure_workspace.draw(self.api.optimiser.getShapeOrientedDilated(), options='g:')
            while g_search.step():
                
                self.api.optimiser.position = g_search.offset
                self.api.optimiser.angle = g_search.angle
                self.figure_workspace.draw(self.api.optimiser.getShapeOriented())
                self.figure_workspace.draw(self.api.optimiser.getShapeOrientedDilated(), options='g:')
            self.figure_workspace.draw(self.api.optimiser.getShapeOriented(), options='r-')
            self.canvasWorkspace.draw()


    def checkUseNFP(self):
        checked = self.cb_optimiser_use_nfp.isChecked()
        self.api.settings.use_nfp = checked
        self.sp_optimiser_nfp_rotations.setEnabled(checked)


    def checkLocalOptimisation(self):
        self.api.settings.local_optimisation = self.cb_optimiser_local_optimisation.isChecked()


    def setNFPRotations(self, number):
        self.api.settings.nfp_rotations = number


    def fillInputList(self, items):
        for item in items:
            self.input_list.append(self.createInputListItem(item))
        self.layout_input_list.addStretch()

    def createInputListItem(self, name):
        """Creates new entry in the gcode list""" #TODO: Refactor
        layout = self.layout_input_list
        gb = MyGroupBox()
        gbl = QtWidgets.QHBoxLayout()
        gb.setLayout(gbl)
        gb.setMouseTracking(True)
        gb.setAttribute(QtCore.Qt.WA_Hover)
        gb.info = name
        gb.click_callback = self.selectAndDrawShape
        
        
        lbl = QtWidgets.QLabel(name)
        splbl = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred,QtWidgets.QSizePolicy.Preferred)
        splbl.setHorizontalStretch(3)
        lbl.setSizePolicy(splbl)
        
        spb = QtWidgets.QSpinBox()
        spspb = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred,QtWidgets.QSizePolicy.Preferred)
        spspb.setHorizontalStretch(1)
        spb.setSizePolicy(spspb)
        spb.valueChanged.connect(lambda x: self.api.setShapeCount(lbl.text(), spb.value()))

        chkb = QtWidgets.QCheckBox("Convex")
        chkb.setChecked(True)
        spchcb = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred,QtWidgets.QSizePolicy.Preferred)
        spchcb.setHorizontalStretch(1)
        chkb.setSizePolicy(spchcb)
        chkb.stateChanged.connect(lambda x: self.api.setShapeConvex(lbl.text(), bool(x)))

        gbl.addWidget(spb)
        gbl.addWidget(lbl)
        gbl.addWidget(chkb)
        layout.addWidget(gb)
        return InputControl(name, spb, chkb)

    def clearInputList(self):
        self.input_list = []
        layout = self.layout_input_list
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def clearInputShapeCounts(self):
        for item in self.input_list:
            item.reset()
            self.api.setShapeCount(item.name, 0)

    ## SETUP ##
    def setupCanvases(self, fPreview, fWorkspace):
        self.figure_preview = fPreview
        self.canvasPreview = FigureCanvas(fPreview.figure)
        self.mplPreviewLayout.addWidget(self.canvasPreview)
        self.canvasPreview.draw()
        self.figure_workspace = fWorkspace
        self.canvasWorkspace = FigureCanvas(fWorkspace.figure)
        self.mplWorkspaceLayout.addWidget(self.canvasWorkspace)
        self.canvasWorkspace.draw()

    def setupCallbacks(self):
        # input control
        self.pb_input_browse.clicked.connect(self.askFolder)
        self.pb_input_clear.clicked.connect(self.clearInputShapeCounts)

        # appy settings
        self.pb_settings_apply.clicked.connect(self.applySettings)

        # workspace menu
        self.menu_workspace_export.triggered.connect(self.workspaceExport)
        self.menu_workspace_import.triggered.connect(self.workspaceImport)

        # canvas control
        self.pb_workspace_add.clicked.connect(self.startDrawing)
        self.pb_workspace_subtract.clicked.connect(self.startSubtracting)
        self.pb_workspace_remove.clicked.connect(self.startDeleting)
        self.pb_workspace_clear.clicked.connect(self.clearWorkspace)
        self.pb_workspace_clear_shapes.clicked.connect(self.clearShapes)

        # optimisation control
        self.progress_bar_optimisation.setVisible(False)

        self.pb_optimiser_start.clicked.connect(self.startOptimisation)
        self.pb_optimiser_stop.clicked.connect(self.api.stopPlacing)
        self.cb_optimiser_use_nfp.clicked.connect(self.checkUseNFP)
        self.cb_optimiser_local_optimisation.clicked.connect(self.checkLocalOptimisation)
        self.sp_optimiser_nfp_rotations.valueChanged.connect(self.setNFPRotations)
        
        # debug
        self.pb_optimiser_debug_add_as_hole.clicked.connect(self.api.optimiser.addShapeAsHole)
        self.pb_optimiser_debug_place_one.clicked.connect(self.debug_placeOneShape)

        # workspace figure callback
        self.canvasWorkspace.mpl_connect('motion_notify_event', self.workspaceMouseMotion)
        self.canvasWorkspace.mpl_connect('button_press_event', self.workspaceMouseClicked)

        

if __name__ == "__main__":
    # import sys

    # import figures
    # figure_preview = figures.Figures()
    # figure_workspace = figures.Figures()

    # app = QtWidgets.QApplication(sys.argv)
    # mainWindow = MainWindow(None)
    # mainWindow.setupCanvases(figure_preview.figure, figure_workspace.figure)
    # mainWindow.setupCallbacks()
    # mainWindow.show()

    # sys.exit(app.exec_())
    import sys 
    sys.path.append('...')
    from main import *