from OCC.Display.SimpleGui import init_display
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB

display, start_display, add_menu, add_function_to_menu = init_display()
display.View.TriedronErase()

step_reader = STEPControl_Reader()
step_reader.ReadFile("test.step")
step_reader.TransferRoot()
shape = step_reader.Shape()

color = Quantity_Color(0.1, 0.1, 0.1, Quantity_TOC_RGB)
display.DisplayColoredShape(shape, color, update=True)

# 等轴测视角 (isometric: x=1, y=-1, z=1)
display.View.SetProj(1, -1, 1)
display.View.FitAll()
display.View.Dump("test_iso.png")
