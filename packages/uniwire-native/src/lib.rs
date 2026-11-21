//! The search of uniwire's grid link router (`uniwire.layout.routing.route_grid`), compiled.
//!
//! Python builds the grid, the cells blocked by texts and symbols, the lines that count when running along each grid
//! line and the lines crossed between two grid lines; this module costs the grid moves and runs the same Dijkstra
//! search as the pure Python one. Every cost is computed with the same floating-point operations in the same order,
//! and the heap pops its entries in the same order (they are compared as the same tuples), so the route found is
//! exactly the one the pure Python search finds.

use pyo3::prelude::*;
use std::cmp::Ordering;
use std::collections::BinaryHeap;

/// A heap entry: (cost, state << 6 | kind << 4 | turns, state before (goal entries only, else -1)), popped smallest
/// first in tuple order, as Python's `heapq` pops the tuples (cost, code[, before]).
#[derive(Clone, Copy)]
struct Entry {
    cost: f64,
    code: u64,
    before: i64,
}

impl PartialEq for Entry {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}

impl Eq for Entry {}

impl PartialOrd for Entry {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Entry {
    fn cmp(&self, other: &Self) -> Ordering {
        // reversed: BinaryHeap pops the largest. Costs are finite and never NaN.
        other
            .cost
            .partial_cmp(&self.cost)
            .unwrap_or(Ordering::Equal)
            .then_with(|| other.code.cmp(&self.code))
            .then_with(|| other.before.cmp(&self.before))
    }
}

/// Lists of `width` floats per grid line: the values of line `n` are `vals[off[n] * width..off[n + 1] * width]`.
struct Ragged<'a> {
    off: &'a [usize],
    vals: &'a [f64],
    width: usize,
}

impl<'a> Ragged<'a> {
    fn get(&self, n: usize) -> &'a [f64] {
        &self.vals[self.off[n] * self.width..self.off[n + 1] * self.width]
    }
}

/// Running from a to b along a grid line whose terms are `lines` (weight, divisor, start, end): `run_cost`.
fn run_cost(a: f64, b: f64, lines: &[f64]) -> f64 {
    let mut c = 0.0;
    for t in lines.chunks_exact(4) {
        let (w, k, v0, v1) = (t[0], t[1], t[2], t[3]);
        if v0 < b && a < v1 {
            c += w * (py_min(v1, b) - py_max(v0, a)) / k;
        }
    }
    c
}

/// Python's min(a, b): the first one unless the second is smaller.
fn py_min(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

/// Python's max(a, b): the first one unless the second is larger.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// The crossings of a move at `pos` over the lines `spans` (start, end): `weight` for each line it crosses, summed
/// first then added (the weights are whole numbers: the sum is exact, as Python's `sum`).
fn crossings(spans: &[f64], pos: f64, weight: f64) -> f64 {
    let mut s = 0.0;
    for t in spans.chunks_exact(2) {
        if t[0] < pos && pos < t[1] {
            s += weight;
        }
    }
    s
}

struct Grid<'a> {
    ny: usize,
    xs: &'a [f64],
    ys: &'a [f64],
    blocked: &'a [u8],
    col: Ragged<'a>,
    row: Ragged<'a>,
    gy_bars: Ragged<'a>,
    gy_sides: Ragged<'a>,
    gy_wires: Ragged<'a>,
    gx_wires: Ragged<'a>,
    gx_sides: Ragged<'a>,
    box_cross: f64,
    length: f64,
    bus_cross: f64,
    frame_cross: f64,
    wire_cross: f64,
}

impl Grid<'_> {
    /// Cost of the move numbered `key`: (lower end i * ny + j) * 2 + axis (1: vertical), as `edge_cost`.
    fn edge_cost(&self, key: usize) -> f64 {
        let cell = key >> 1;
        let (i, j) = (cell / self.ny, cell % self.ny);
        let mut c;
        if key & 1 == 1 {
            c = if self.blocked[cell] != 0 || self.blocked[cell + 1] != 0 {
                self.box_cross
            } else {
                0.0
            };
            let (x, a, b) = (self.xs[i], self.ys[j], self.ys[j + 1]);
            let lines = self.col.get(i);
            c += self.length * (b - a)
                + if lines.is_empty() {
                    0.0
                } else {
                    run_cost(a, b, lines)
                };
            let bars = self.gy_bars.get(j);
            if !bars.is_empty() {
                c += crossings(bars, x, self.bus_cross);
            }
            let sides = self.gy_sides.get(j);
            if !sides.is_empty() {
                c += crossings(sides, x, self.frame_cross);
            }
            let wires = self.gy_wires.get(j);
            if !wires.is_empty() {
                c += crossings(wires, x, self.wire_cross);
            }
        } else {
            c = if self.blocked[cell] != 0 || self.blocked[cell + self.ny] != 0 {
                self.box_cross
            } else {
                0.0
            };
            let (y, a, b) = (self.ys[j], self.xs[i], self.xs[i + 1]);
            let lines = self.row.get(j);
            c += self.length * (b - a)
                + if lines.is_empty() {
                    0.0
                } else {
                    run_cost(a, b, lines)
                };
            let wires = self.gx_wires.get(i);
            if !wires.is_empty() {
                c += crossings(wires, y, self.wire_cross);
            }
            let sides = self.gx_sides.get(i);
            if !sides.is_empty() {
                c += crossings(sides, y, self.frame_cross);
            }
        }
        c
    }
}

/// The cheapest route on the grid, as the search of `route_grid`.
///
/// `starts`: (state, end index) of each start, in order; `goals`: (state, end index, move after it or -1) of each
/// goal, in order (a later one at the same state replaces an earlier one, as in a dict); `wind_turns`, `wind_wrap`:
/// `_wind(t, d, d2)` for t * 16 + d * 4 + d2. Returns None (no route) or (the states from the goal back to the start,
/// the index of the start used, the cost to report).
#[pyfunction]
#[pyo3(signature = (nx, ny, xs, ys, blocked, col, row, gy_bars, gy_sides, gy_wires, gx_wires, gx_sides,
                    box_cross, length, bend, wrap, bus_cross, frame_cross, wire_cross, starts, goals,
                    wind_turns, wind_wrap))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn grid_search(
    py: Python<'_>,
    nx: usize,
    ny: usize,
    xs: Vec<f64>,
    ys: Vec<f64>,
    blocked: &[u8],
    col: (Vec<usize>, Vec<f64>),
    row: (Vec<usize>, Vec<f64>),
    gy_bars: (Vec<usize>, Vec<f64>),
    gy_sides: (Vec<usize>, Vec<f64>),
    gy_wires: (Vec<usize>, Vec<f64>),
    gx_wires: (Vec<usize>, Vec<f64>),
    gx_sides: (Vec<usize>, Vec<f64>),
    box_cross: f64,
    length: f64,
    bend: f64,
    wrap: f64,
    bus_cross: f64,
    frame_cross: f64,
    wire_cross: f64,
    starts: Vec<(usize, i64)>,
    goals: Vec<(usize, i64, i64)>,
    wind_turns: Vec<u8>,
    wind_wrap: Vec<u8>,
) -> PyResult<Option<(Vec<usize>, i64, f64)>> {
    let check = |r: &(Vec<usize>, Vec<f64>), n: usize, width: usize, what: &str| -> PyResult<()> {
        let ok = r.0.len() == n + 1
            && r.0.windows(2).all(|w| w[0] <= w[1])
            && r.0.last().is_some_and(|&e| e * width == r.1.len());
        if ok {
            Ok(())
        } else {
            Err(pyo3::exceptions::PyValueError::new_err(format!(
                "grid_search: bad {what}"
            )))
        }
    };
    check(&col, nx, 4, "col")?;
    check(&row, ny, 4, "row")?;
    check(&gy_bars, ny, 2, "gy_bars")?;
    check(&gy_sides, ny, 2, "gy_sides")?;
    check(&gy_wires, ny, 2, "gy_wires")?;
    check(&gx_wires, nx, 2, "gx_wires")?;
    check(&gx_sides, nx, 2, "gx_sides")?;
    let size = nx * ny * 4;
    if xs.len() != nx
        || ys.len() != ny
        || blocked.len() != nx * ny
        || wind_turns.len() != 256
        || wind_wrap.len() != 256
        || starts.iter().any(|s| s.0 >= size)
        || goals.iter().any(|g| g.0 >= size || g.2 > 3)
    {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "grid_search: bad arguments",
        ));
    }
    let grid = Grid {
        ny,
        xs: &xs,
        ys: &ys,
        blocked,
        col: Ragged {
            off: &col.0,
            vals: &col.1,
            width: 4,
        },
        row: Ragged {
            off: &row.0,
            vals: &row.1,
            width: 4,
        },
        gy_bars: Ragged {
            off: &gy_bars.0,
            vals: &gy_bars.1,
            width: 2,
        },
        gy_sides: Ragged {
            off: &gy_sides.0,
            vals: &gy_sides.1,
            width: 2,
        },
        gy_wires: Ragged {
            off: &gy_wires.0,
            vals: &gy_wires.1,
            width: 2,
        },
        gx_wires: Ragged {
            off: &gx_wires.0,
            vals: &gx_wires.1,
            width: 2,
        },
        gx_sides: Ragged {
            off: &gx_sides.0,
            vals: &gx_sides.1,
            width: 2,
        },
        box_cross,
        length,
        bus_cross,
        frame_cross,
        wire_cross,
    };
    let wind = |t: u64, d: usize, d2: usize| -> (u64, u64) {
        let n = (t as usize) * 16 + d * 4 + d2;
        (wind_turns[n] as u64, wind_wrap[n] as u64)
    };
    Ok(py.detach(|| {
        let mut goal_at: Vec<i64> = vec![-1; size]; // the goal index at a state, -1: none
        let mut goal_then: Vec<i64> = vec![-1; size];
        for &(s, k, then) in &goals {
            goal_at[s] = k;
            goal_then[s] = then;
        }
        let mut origin: Vec<i64> = vec![0; size];
        let mut prev: Vec<i64> = vec![-1; size];
        let mut dist: Vec<f64> = vec![1e18; size];
        let mut turns: Vec<u64> = vec![0; size];
        let mut cache: Vec<f64> = vec![f64::NAN; nx * ny * 2];
        let mut heap: BinaryHeap<Entry> = BinaryHeap::new();
        for &(st, k) in &starts {
            dist[st] = 0.0;
            prev[st] = -1;
            origin[st] = k;
            heap.push(Entry {
                cost: 0.0,
                code: (st as u64) << 6 | 16,
                before: -1,
            });
        }
        // the moves from a state, as in Python: (direction, step of the cell number, step of the edge key)
        let ny_i = ny as i64;
        let px = (0usize, ny_i, 0i64);
        let mx = (1usize, -ny_i, -2 * ny_i);
        let py_ = (2usize, 1i64, 1i64);
        let my = (3usize, -1i64, -1i64);
        let moves: [[(usize, i64, i64); 3]; 4] =
            [[px, py_, my], [mx, py_, my], [px, mx, py_], [px, mx, my]];
        let straight: [(usize, i64, i64); 4] = [px, mx, py_, my];
        let (last_i, last_j) = (nx - 1, ny - 1);
        let mut found: i64 = -1;
        let mut last: i64 = -1;
        let mut cost = 0.0;
        while let Some(item) = heap.pop() {
            cost = item.cost;
            let code = item.code;
            let st = (code >> 6) as usize;
            let fresh = (code >> 4) & 3;
            if fresh == 2 {
                found = st as i64;
                last = item.before;
                break;
            }
            if cost > dist[st] {
                continue;
            }
            let t = code & 15;
            if wrap != 0.0 {
                if t != turns[st] {
                    continue;
                }
            } else if fresh == 0 && goal_at[st] >= 0 {
                found = st as i64;
                break;
            }
            let d = st & 3;
            let cell = st >> 2;
            let (i, j) = (cell / ny, cell % ny);
            let opts: &[(usize, i64, i64)] = if fresh == 1 {
                std::slice::from_ref(&straight[d])
            } else {
                &moves[d]
            };
            for &(d2, dc, dk) in opts {
                let edge_ok = match d2 {
                    0 => i != last_i,
                    1 => i != 0,
                    2 => j != last_j,
                    _ => j != 0,
                };
                if !edge_ok {
                    continue;
                }
                let key = ((cell * 2) as i64 + dk) as usize;
                let mut e = cache[key];
                if e.is_nan() {
                    e = grid.edge_cost(key);
                    cache[key] = e;
                }
                let mut c = cost + e + if d2 != d { bend } else { 0.0 };
                let s2 = (((cell as i64) + dc) as usize) * 4 + d2;
                if wrap != 0.0 {
                    let mut t2 = t;
                    if fresh == 0 && d2 != d {
                        let (w2, k) = wind(t, d, d2);
                        t2 = w2;
                        c += wrap * k as f64;
                    }
                    if goal_at[s2] >= 0 {
                        let nxt = goal_then[s2];
                        let k = if nxt >= 0 {
                            wind(t2, d2, nxt as usize).1
                        } else {
                            0
                        };
                        heap.push(Entry {
                            cost: c + wrap * k as f64,
                            code: (s2 as u64) << 6 | 32 | t2,
                            before: st as i64,
                        });
                    }
                    if c < dist[s2] {
                        dist[s2] = c;
                        prev[s2] = st as i64;
                        origin[s2] = origin[st];
                        turns[s2] = t2;
                        heap.push(Entry {
                            cost: c,
                            code: (s2 as u64) << 6 | t2,
                            before: -1,
                        });
                    }
                } else if c < dist[s2] {
                    dist[s2] = c;
                    prev[s2] = st as i64;
                    origin[s2] = origin[st];
                    heap.push(Entry {
                        cost: c,
                        code: (s2 as u64) << 6,
                        before: -1,
                    });
                }
            }
        }
        if found < 0 {
            return None;
        }
        let reported = if wrap != 0.0 {
            cost
        } else {
            dist[found as usize]
        };
        let mut chain: Vec<usize> = Vec::new();
        let mut s = found;
        if wrap != 0.0 {
            chain.push(found as usize);
            s = last;
        }
        let mut first = s;
        while s >= 0 {
            chain.push(s as usize);
            if prev[s as usize] < 0 {
                first = s;
            }
            s = prev[s as usize];
        }
        Some((chain, origin[first as usize], reported))
    }))
}

#[pymodule]
fn uniwire_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    // the interface of grid_search: uniwire uses this module only when it was built for the same one
    m.add("GRID_API", 1)?;
    m.add_function(wrap_pyfunction!(grid_search, m)?)?;
    Ok(())
}
