"""Automatic layout of a single-line diagram.

Principle (radial tree, power flowing top to bottom):

1. width (post-order): a leaf = one column (``pitch``), a node = sum of its children;
2. x coordinates (pre-order): children are placed left to right, the parent sits directly above
   its first child (the busbar extends to the right);
3. y coordinates (pre-order): symbols are stacked, a busbar goes under every node with several
   children, then nested board frames are shifted so they do not overlap;
4. all loads are aligned on a common baseline, below which sits the
   feeder table (one column per feeder);
5. secondary sources (transfer switch) are placed to the right of their entry point, ties are aligned;
6. split into sheets if the required reduction exceeds ``view.min_scale``: several trees side by side are cut into
   groups that each fit, a tree and the supplies drawn beside it together (links between groups end on off-page
   references); then a sub-distribution board goes to a dedicated sheet (off-page reference), otherwise the busbar
   is cut into continuation sheets;
7. auxiliary devices go on the sheet of the node they are linked to, in the nearest free space; links are routed
   through horizontal channels clear of texts and symbols (:mod:`uniwire.layout.routing`), and a link to a node
   drawn on another sheet ends on an off-page reference.
"""

from .engine import LNode, SheetLayout, SheetSpec, layout_sheet, plan_sheets

__all__ = ["LNode", "SheetLayout", "SheetSpec", "layout_sheet", "plan_sheets"]
