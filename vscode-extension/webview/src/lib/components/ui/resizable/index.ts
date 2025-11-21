import {
  PaneGroup as PaneGroupPrimitive,
  PaneResizer as PaneResizerPrimitive,
  Pane as PanePrimitive,
} from "paneforge";

const PaneGroup = PaneGroupPrimitive;
const PaneResizer = PaneResizerPrimitive;
const Pane = PanePrimitive;

export {
  PaneGroup,
  PaneResizer,
  Pane,
  //
  PaneGroup as ResizablePanelGroup,
  PaneResizer as ResizableHandle,
  Pane as ResizablePanel,
};
