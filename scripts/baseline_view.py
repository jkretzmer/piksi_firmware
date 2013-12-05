from traits.api import Instance, Dict, HasTraits, Array, Float, on_trait_change, List, Int, Button, Bool
from traitsui.api import Item, View, HGroup, VGroup, ArrayEditor, HSplit, TabularEditor
from traitsui.tabular_adapter import TabularAdapter
from chaco.api import ArrayPlotData, Plot
from chaco.tools.api import ZoomTool, PanTool
from enable.api import ComponentEditor
from enable.savage.trait_defs.ui.svg_button import SVGButton
from pyface.api import GUI

import struct
import math
import os
import numpy as np
import datetime

import sbp_messages as ids

class SimpleAdapter(TabularAdapter):
    columns = [('Item', 0), ('Value',  1)]
    width = 80

class Baseline:
  def from_binary(self, data):
    soln = struct.unpack('<3ddHHB', data)
    self.ned = np.array([soln[0], soln[1], soln[2]])
    self.tow = soln[3]
    self.wn = soln[4]
    self.flags = soln[5]
    self.n_sats = soln[6]

class BaselineView(HasTraits):
  python_console_cmds = Dict()

  ns = List()
  es = List()
  ds = List()

  table = List()

  plot = Instance(Plot)
  plot_data = Instance(ArrayPlotData)

  running = Bool(True)
  position_centered = Bool(False)

  clear_button = SVGButton(
    label='', tooltip='Clear',
    filename=os.path.join(os.path.dirname(__file__), 'images', 'x.svg'),
    width=16, height=16
  )
  zoomall_button = SVGButton(
    label='', tooltip='Zoom All',
    filename=os.path.join(os.path.dirname(__file__), 'images', 'fullscreen.svg'),
    width=16, height=16
  )
  center_button = SVGButton(
    label='', tooltip='Center on Baseline', toggle=True,
    filename=os.path.join(os.path.dirname(__file__), 'images', 'target.svg'),
    width=16, height=16
  )
  paused_button = SVGButton(
    label='', tooltip='Pause', toggle_tooltip='Run', toggle=True,
    filename=os.path.join(os.path.dirname(__file__), 'images', 'pause.svg'),
    toggle_filename=os.path.join(os.path.dirname(__file__), 'images', 'play.svg'),
    width=16, height=16
  )

  init_button = Button(label='Init Ambs.')

  traits_view = View(
    HSplit(
      Item('table', style = 'readonly', editor = TabularEditor(adapter=SimpleAdapter()), show_label=False, width=0.3),
      VGroup(
        HGroup(
          Item('paused_button', show_label=False),
          Item('clear_button', show_label=False),
          Item('zoomall_button', show_label=False),
          Item('center_button', show_label=False),
          Item('init_button', show_label=False),
        ),
        Item(
          'plot',
          show_label = False,
          editor = ComponentEditor(bgcolor = (0.8,0.8,0.8)),
        )
      )
    )
  )

  def _zoomall_button_fired(self):
    self.plot.index_range.low_setting = 'auto'
    self.plot.index_range.high_setting = 'auto'
    self.plot.value_range.low_setting = 'auto'
    self.plot.value_range.high_setting = 'auto'

  def _center_button_fired(self):
    self.position_centered = not self.position_centered

  def _paused_button_fired(self):
    self.running = not self.running

  def _init_button_fired(self):
    self.link.send_message(0x99, '')

  def _clear_button_fired(self):
    self.ns = []
    self.es = []
    self.ds = []
    self.plot_data.set_data('n', [])
    self.plot_data.set_data('e', [])
    self.plot_data.set_data('d', [])
    self.plot_data.set_data('t', [])

  def _baseline_callback(self, data):
    # Updating an ArrayPlotData isn't thread safe (see chaco issue #9), so
    # actually perform the update in the UI thread.
    if self.running:
      GUI.invoke_later(self.baseline_callback, data)

  def update_table(self):
    self._table_list = self.table.items()

  def baseline_callback(self, data):
    soln = Baseline()
    soln.from_binary(data)
    table = []

    t = datetime.datetime(1980, 1, 5) + \
        datetime.timedelta(weeks=soln.wn) + \
        datetime.timedelta(seconds=soln.tow)
    table.append(('GPS Time', str(t)))

    table.append(('N', soln.ned[0]))
    table.append(('E', soln.ned[1]))
    table.append(('D', soln.ned[2]))
    table.append(('Dist.', np.sqrt(soln.ned.dot(soln.ned))))
    table.append(('Num. Sats.', soln.n_sats))
    table.append(('Flags', '0x' + hex(soln.flags)))

    self.ns.append(soln.ned[0])
    self.es.append(soln.ned[1])
    self.ds.append(soln.ned[2])

    self.ns = self.ns[:100]
    self.es = self.es[:100]
    self.ds = self.ds[:100]

    self.plot_data.set_data('n', self.ns)
    self.plot_data.set_data('e', self.es)
    self.plot_data.set_data('d', self.ds)
    self.plot_data.set_data('ref_n', [0.0, soln.ned[0]])
    self.plot_data.set_data('ref_e', [0.0, soln.ned[1]])
    self.plot_data.set_data('ref_d', [0.0, soln.ned[2]])
    t = range(len(self.ns))
    self.plot_data.set_data('t', t)

    if self.position_centered:
      d = (self.plot.index_range.high - self.plot.index_range.low) / 2.
      self.plot.index_range.set_bounds(soln.ned[0] - d, soln.ned[0] + d)
      d = (self.plot.value_range.high - self.plot.value_range.low) / 2.
      self.plot.value_range.set_bounds(soln.ned[1] - d, soln.ned[1] + d)

    self.table = table

  def __init__(self, link):
    super(BaselineView, self).__init__()

    self.plot_data = ArrayPlotData(n=[0.0], e=[0.0], d=[0.0], t=[0.0], ref_n=[0.0], ref_e=[0.0], ref_d=[0.0])
    self.plot = Plot(self.plot_data)

    self.plot.plot(('e', 'n'), type='line', name='line', color=(0, 0, 0, 0.1))
    self.plot.plot(('e', 'n'), type='scatter', name='points', color='blue', marker='dot', line_width=0.0, marker_size=1.0)
    self.plot.plot(('ref_e', 'ref_n'),
        type='scatter',
        color='red',
        marker='plus',
        marker_size=5,
        line_width=1.5
    )

    self.plot.index_axis.tick_label_position = 'inside'
    self.plot.index_axis.tick_label_color = 'gray'
    self.plot.index_axis.tick_color = 'gray'
    self.plot.value_axis.tick_label_position = 'inside'
    self.plot.value_axis.tick_label_color = 'gray'
    self.plot.value_axis.tick_color = 'gray'
    self.plot.padding = (0, 1, 0, 1)

    self.plot.tools.append(PanTool(self.plot))
    zt = ZoomTool(self.plot, zoom_factor=1.1, tool_mode="box", always_on=False)
    self.plot.overlays.append(zt)

    self.link = link
    self.link.add_callback(ids.BASELINE, self._baseline_callback)

    self.python_console_cmds = {
      'baseline': self
    }

