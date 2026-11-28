"""
Visualisasi Knowledge Base Tree — generate diagram dari data Supabase.

Output:
  1. Print hierarki tree ke terminal (4 tree: kategori, pola, perusahaan, invoice)
  2. Export ke PNG untuk lampiran skripsi (layout vertikal, readable)

Jalankan:
    python src/visualisasi_kb_tree.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import textwrap

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from supabase import create_client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
sb = create_client(url, key)

CLIENT_ID = "a1b2c3d4-0001-4000-8000-000000000001"

OUTPUT_DIR = ROOT / "docs" / "kb_diagrams"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    nodes = sb.table("tree_nodes").select("*").eq("client_id", CLIENT_ID).execute().data
    mappings = sb.table("mapping_layer").select("*").eq("client_id", CLIENT_ID).execute().data
    acc_maps = sb.table("account_mapping").select("*").eq("client_id", CLIENT_ID).execute().data
    return nodes, mappings, acc_maps


def build_tree(nodes, tree_type):
    filtered = [n for n in nodes if n["tree_type"] == tree_type]
    by_id = {n["id"]: n for n in filtered}
    children = {}
    roots = []
    for n in filtered:
        pid = n.get("parent_id")
        if pid and pid in by_id:
            children.setdefault(pid, []).append(n)
        else:
            roots.append(n)
    roots.sort(key=lambda n: (n["level"], n.get("kode", "")))
    for clist in children.values():
        clist.sort(key=lambda n: (n["level"], n.get("kode", "")))
    return roots, children, by_id


def print_tree(roots, children, indent=0, mapping_index=None, max_children=None):
    for i, node in enumerate(roots):
        is_last = (i == len(roots) - 1)
        prefix = "    " * indent + ("└── " if is_last else "├── ")
        meta = node.get("metadata", {})
        kode_akun = meta.get("kode_akun", "")
        keywords = meta.get("keywords", [])

        label = node["nama"]
        extras = []
        if node.get("kode") and not node["kode"].startswith(("POLA_", "GRUP_", "INT_", "CUST_", "VEND_")):
            extras.append(node["kode"])
        if kode_akun and kode_akun != "PERLU_REVIEW":
            extras.append(f"CoA: {kode_akun}")
        if kode_akun == "PERLU_REVIEW":
            extras.append("PERLU REVIEW")
        if keywords:
            extras.append(f"keywords: {keywords}")

        if mapping_index and node["id"] in mapping_index:
            m = mapping_index[node["id"]]
            extras.append(f"-> {m['target_nama']} (conf: {m['confidence']})")

        suffix = f"  [{', '.join(extras)}]" if extras else ""
        print(f"{prefix}{label}{suffix}")

        kids = children.get(node["id"], [])
        if max_children and len(kids) > max_children:
            print_tree(kids[:max_children], children, indent + 1, mapping_index)
            remaining = len(kids) - max_children
            pad = "    " * (indent + 1) + "└── "
            print(f"{pad}... dan {remaining} lainnya")
        else:
            print_tree(kids, children, indent + 1, mapping_index)


def build_mapping_index(mappings, nodes_by_id):
    index = {}
    for m in mappings:
        src = m["source_node_id"]
        tgt = m["target_node_id"]
        tgt_node = nodes_by_id.get(tgt)
        index[src] = {
            "target_id": tgt,
            "target_nama": tgt_node["nama"] if tgt_node else "?",
            "confidence": m.get("confidence", 0),
            "relation_type": m["relation_type"],
        }
    return index


# ---- PNG Diagram Generation (vertical layout) ----

TREE_COLORS = {
    "kategori": {"fill": "#E8F5E9", "border": "#2E7D32", "root_fill": "#2E7D32", "font": "#1B5E20", "title": "#2E7D32", "line": "#66BB6A"},
    "pola": {"fill": "#FFF3E0", "border": "#E65100", "root_fill": "#E65100", "font": "#BF360C", "title": "#E65100", "line": "#FFA726"},
    "perusahaan": {"fill": "#E3F2FD", "border": "#1565C0", "root_fill": "#1565C0", "font": "#0D47A1", "title": "#1565C0", "line": "#42A5F5"},
    "invoice": {"fill": "#F3E5F5", "border": "#6A1B9A", "root_fill": "#6A1B9A", "font": "#4A148C", "title": "#6A1B9A", "line": "#AB47BC"},
}



def _make_label(node, include_keywords=False):
    meta = node.get("metadata", {})
    kode_akun = meta.get("kode_akun", "")
    keywords = meta.get("keywords", [])
    lines = [node["nama"]]
    if kode_akun and kode_akun != "PERLU_REVIEW":
        lines.append(f"CoA: {kode_akun}")
    elif kode_akun == "PERLU_REVIEW":
        lines.append("PERLU REVIEW")
    if include_keywords and keywords:
        kw_str = ", ".join(keywords[:3])
        if len(keywords) > 3:
            kw_str += f" +{len(keywords)-3}"
        lines.append(f"[{kw_str}]")
    return "\n".join(lines)


def _draw_rounded_box(ax, cx, cy, w, h, text, fc, ec, tc, fontsize=8, bold=False, radius=0.12):
    rect = mpatches.FancyBboxPatch(
        (cx - w/2, cy - h/2), w, h,
        boxstyle=f"round,pad={radius}",
        facecolor=fc, edgecolor=ec, linewidth=1.5, zorder=2
    )
    ax.add_patch(rect)
    new_lines = []
    for line in text.split("\n"):
        if len(line) > 30:
            new_lines.extend(textwrap.wrap(line, 28))
        else:
            new_lines.append(line)
    wrapped = "\n".join(new_lines)
    ax.text(cx, cy, wrapped, ha="center", va="center", fontsize=fontsize,
            color=tc, fontweight="bold" if bold else "normal",
            zorder=3, linespacing=1.3, fontfamily="sans-serif")


def _layout_horizontal(roots, children, max_leaf=None):
    """
    Horizontal tree: root on LEFT, children expand to the RIGHT.
    Each node gets (cx, cy) where cx = depth (left→right), cy = row (top→bottom).
    Returns {node_id: (cx, cy, label, depth)} and edges list.
    """
    NODE_COL_W = 4.0   # horizontal spacing between levels
    ROW_H = 0.9        # vertical spacing between sibling rows

    positions = {}
    edges = []
    y_cursor = [0.0]

    def layout(node, depth, include_kw=False):
        kids = children.get(node["id"], [])
        truncated = False
        if max_leaf and len(kids) > max_leaf and all(not children.get(k["id"]) for k in kids):
            visible = kids[:max_leaf]
            truncated = True
        else:
            visible = kids

        child_ys = []
        for k in visible:
            layout(k, depth + 1, include_kw)
            child_ys.append(positions[k["id"]][1])
            edges.append((node["id"], k["id"]))

        if truncated:
            etc_id = f"_etc_{node['id']}"
            ey = y_cursor[0]
            y_cursor[0] += ROW_H
            positions[etc_id] = ((depth + 1) * NODE_COL_W, ey, f"+{len(kids) - max_leaf} lainnya", -1)
            edges.append((node["id"], etc_id))
            child_ys.append(ey)

        if child_ys:
            cy = (min(child_ys) + max(child_ys)) / 2.0
        else:
            cy = y_cursor[0]
            y_cursor[0] += ROW_H

        cx = depth * NODE_COL_W
        label = _make_label(node, include_keywords=include_kw)
        positions[node["id"]] = (cx, cy, label, depth)

    for r in roots:
        include_kw = any(n.get("metadata", {}).get("keywords") for n in children.get(r["id"], []))
        layout(r, 0, include_kw)
        y_cursor[0] += 0.4

    return positions, edges


def generate_tree_png(tree_type, roots, children, output_path, max_leaf=10):
    colors = TREE_COLORS.get(tree_type, TREE_COLORS["kategori"])
    positions, edges = _layout_horizontal(roots, children, max_leaf)

    if not positions:
        return

    BOX_W = 3.2
    BOX_H = 0.65

    all_cx = [p[0] for p in positions.values()]
    all_cy = [p[1] for p in positions.values()]

    margin_x = BOX_W * 0.8
    margin_y = BOX_H + 0.3

    x_min, x_max = min(all_cx) - margin_x, max(all_cx) + margin_x
    y_min, y_max = min(all_cy) - margin_y, max(all_cy) + margin_y

    data_w = x_max - x_min
    data_h = y_max - y_min

    fig_w = max(10, data_w * 0.9)
    fig_h = max(6, data_h * 1.1)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_max, y_min)  # top=0
    ax.set_aspect("auto")
    ax.axis("off")

    total = len([k for k in positions if not k.startswith("_etc_")])
    ax.set_title(
        f"Knowledge Base — Tree {tree_type.title()}\n({total} nodes)",
        fontsize=16, fontweight="bold", color=colors["title"], pad=16
    )

    # Draw edges: horizontal elbow connectors (parent right edge → child left edge)
    for src_id, tgt_id in edges:
        if src_id in positions and tgt_id in positions:
            x1, y1 = positions[src_id][0], positions[src_id][1]
            x2, y2 = positions[tgt_id][0], positions[tgt_id][1]
            mid_x = (x1 + x2) / 2
            ax.plot([x1 + BOX_W/2, mid_x, mid_x, x2 - BOX_W/2],
                    [y1, y1, y2, y2],
                    color=colors["line"], linewidth=1.2, alpha=0.5, zorder=1,
                    solid_capstyle="round")

    # Draw nodes
    for nid, (cx, cy, label, depth) in positions.items():
        if nid.startswith("_etc_"):
            ax.text(cx, cy, label, ha="center", va="center", fontsize=9,
                    color="#999", fontstyle="italic", zorder=3)
            continue

        is_root = (depth == 0)
        fc = colors["root_fill"] if is_root else colors["fill"]
        tc = "white" if is_root else colors["font"]
        ec = colors["border"]
        fs = 10 if is_root else 8

        n_lines = label.count("\n") + 1
        box_h = max(BOX_H, 0.25 + 0.2 * n_lines)
        _draw_rounded_box(ax, cx, cy, BOX_W, box_h, label, fc, ec, tc, fs, bold=is_root)

    plt.tight_layout()
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  -> Saved: {output_path}")


def generate_flow_png(nodes, mappings, output_path):
    """Forward Chaining flow: Pola (left) -> Kategori (right) with arrows."""
    pola_nodes = sorted(
        [n for n in nodes if n["tree_type"] == "pola" and n["level"] == 1],
        key=lambda n: n["nama"]
    )
    mapping_by_src = {}
    for m in mappings:
        if m["relation_type"] == "pola_ke_kategori":
            mapping_by_src[m["source_node_id"]] = m

    nodes_by_id = {n["id"]: n for n in nodes}
    target_ids = set()
    for m in mapping_by_src.values():
        target_ids.add(m["target_node_id"])

    kat_nodes = sorted(
        [n for n in nodes if n["id"] in target_ids],
        key=lambda n: n["nama"]
    )

    n_pola = len(pola_nodes)
    n_kat = len(kat_nodes)
    n_rows = max(n_pola, n_kat, 1)

    row_h = 1.0
    fig_h = max(8, n_rows * row_h + 3)
    fig, ax = plt.subplots(figsize=(18, fig_h))
    ax.set_xlim(-1, 13)
    ax.set_ylim(n_rows * row_h + 1, -1.5)
    ax.axis("off")
    ax.set_title(
        "Knowledge Base — Forward Chaining Flow\n"
        "Tree Pola → Mapping Layer → Tree Kategori → Kode Akun ERP",
        fontsize=14, fontweight="bold", color="#333", pad=16
    )

    # Column headers
    ax.text(2.5, -0.8, "TREE POLA (Keyword Patterns)", ha="center", fontsize=11,
            fontweight="bold", color="#E65100")
    ax.text(10.5, -0.8, "TREE KATEGORI (Akun)", ha="center", fontsize=11,
            fontweight="bold", color="#2E7D32")

    pola_x = 2.5
    kat_x = 10.5
    bw = 4.0
    bh = 0.7

    pola_pos = {}
    for i, n in enumerate(pola_nodes):
        y = i * row_h
        meta = n.get("metadata", {})
        kws = meta.get("keywords", [])
        kw_str = ", ".join(kws[:3])
        if len(kws) > 3:
            kw_str += f" +{len(kws)-3}"
        label = f"{n['nama']}\n[{kw_str}]" if kws else n["nama"]
        _draw_rounded_box(ax, pola_x, y, bw, bh, label, "#FFF3E0", "#E65100", "#BF360C", 8)
        pola_pos[n["id"]] = (pola_x + bw/2, y)

    kat_pos = {}
    for i, n in enumerate(kat_nodes):
        y = i * (n_rows / max(n_kat, 1)) * row_h
        meta = n.get("metadata", {})
        kode_akun = meta.get("kode_akun", "")
        label = n["nama"]
        if kode_akun and kode_akun != "PERLU_REVIEW":
            label += f"\nCoA: {kode_akun}"
        elif kode_akun == "PERLU_REVIEW":
            label += "\nPERLU REVIEW"
        _draw_rounded_box(ax, kat_x, y, bw, bh, label, "#E8F5E9", "#2E7D32", "#1B5E20", 8)
        kat_pos[n["id"]] = (kat_x - bw/2, y)

    for src_id, m in mapping_by_src.items():
        if src_id in pola_pos and m["target_node_id"] in kat_pos:
            x1, y1 = pola_pos[src_id]
            x2, y2 = kat_pos[m["target_node_id"]]
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                        arrowprops=dict(arrowstyle="-|>", color="#FF5722",
                                        lw=1.0, alpha=0.5,
                                        connectionstyle="arc3,rad=0.1"),
                        zorder=1)

    plt.tight_layout()
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  -> Saved: {output_path}")


def generate_overview_png(nodes, mappings, acc_maps, output_path):
    """Overview diagram: 4 trees + mapping layer + account mapping."""
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(8, 0)
    ax.axis("off")
    ax.set_title(
        "Knowledge Base Architecture — SIREKON\n"
        "4 Tree + Mapping Layer + Account Mapping",
        fontsize=15, fontweight="bold", color="#333", pad=16
    )

    tree_counts = {}
    for tt in ["kategori", "pola", "perusahaan", "invoice"]:
        tree_counts[tt] = len([n for n in nodes if n["tree_type"] == tt])

    # 4 tree boxes in a row
    trees = [
        ("Tree Kategori", tree_counts["kategori"], "#E8F5E9", "#2E7D32", "Expense / Income\nhierarchy"),
        ("Tree Pola", tree_counts["pola"], "#FFF3E0", "#E65100", "Keyword patterns\nuntuk matching"),
        ("Tree Perusahaan", tree_counts["perusahaan"], "#E3F2FD", "#1565C0", "Vendor / Customer\n/ Internal"),
        ("Tree Invoice", tree_counts["invoice"], "#F3E5F5", "#6A1B9A", "Invoice numbers\n(empty)"),
    ]

    for i, (name, count, fc, ec, desc) in enumerate(trees):
        cx = 1.75 + i * 3.2
        cy = 1.5
        _draw_rounded_box(ax, cx, cy, 2.8, 1.4,
                          f"{name}\n({count} nodes)\n{desc}",
                          fc, ec, ec, fontsize=9, bold=False)

    # Mapping layer box
    _draw_rounded_box(ax, 7, 4.0, 10, 1.0,
                      f"Mapping Layer — {len(mappings)} relasi cross-domain\n"
                      f"(pola_ke_kategori, perusahaan_ke_kategori)",
                      "#FFF9C4", "#F9A825", "#5D4037", fontsize=9)

    # Account mapping
    _draw_rounded_box(ax, 7, 5.8, 10, 0.9,
                      f"Account Mapping — {len(acc_maps)} kode transaksi → kode akun ERP",
                      "#FCE4EC", "#C62828", "#B71C1C", fontsize=9)

    # Output
    _draw_rounded_box(ax, 7, 7.2, 10, 0.9,
                      "Output: Auto Match | Suggestion | Not Found\n"
                      "(NLP confidence >= 0.72 → Auto Match)",
                      "#E0E0E0", "#616161", "#212121", fontsize=9)

    # Arrows
    for i in range(4):
        cx = 1.75 + i * 3.2
        ax.annotate("", xy=(cx, 3.5), xytext=(cx, 2.2),
                    arrowprops=dict(arrowstyle="-|>", color="#888", lw=1.5), zorder=1)

    ax.annotate("", xy=(7, 5.3), xytext=(7, 4.5),
                arrowprops=dict(arrowstyle="-|>", color="#888", lw=1.5), zorder=1)
    ax.annotate("", xy=(7, 6.75), xytext=(7, 6.25),
                arrowprops=dict(arrowstyle="-|>", color="#888", lw=1.5), zorder=1)

    plt.tight_layout()
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  -> Saved: {output_path}")


def main():
    print("=" * 60)
    print("  VISUALISASI KNOWLEDGE BASE TREE — SIREKON")
    print("=" * 60)

    nodes, mappings, acc_maps = load_data()
    nodes_by_id = {n["id"]: n for n in nodes}
    mapping_index = build_mapping_index(mappings, nodes_by_id)

    total_nodes = len(nodes)
    total_mappings = len(mappings)
    total_acc = len(acc_maps)
    print(f"\nTotal data: {total_nodes} nodes, {total_mappings} mappings, {total_acc} account mappings")

    for tree_type in ["kategori", "pola", "perusahaan", "invoice"]:
        filtered = [n for n in nodes if n["tree_type"] == tree_type]
        if not filtered:
            print(f"\n--- Tree {tree_type.upper()}: (kosong) ---")
            continue

        roots, children, by_id = build_tree(nodes, tree_type)
        mi = mapping_index if tree_type == "pola" else None
        max_c = 6 if tree_type == "perusahaan" else None

        print(f"\n{'='*50}")
        print(f"  TREE {tree_type.upper()} ({len(filtered)} nodes)")
        print(f"{'='*50}")
        print_tree(roots, children, mapping_index=mi, max_children=max_c)

        max_l = 6 if tree_type == "perusahaan" else 10
        out_path = OUTPUT_DIR / f"tree_{tree_type}.png"
        generate_tree_png(tree_type, roots, children, out_path, max_leaf=max_l)

    # Forward chaining flow
    combined_path = OUTPUT_DIR / "forward_chaining_flow.png"
    generate_flow_png(nodes, mappings, combined_path)
    print(f"\n  FORWARD CHAINING FLOW -> {combined_path}")

    # Architecture overview
    overview_path = OUTPUT_DIR / "kb_architecture_overview.png"
    generate_overview_png(nodes, mappings, acc_maps, overview_path)
    print(f"  ARCHITECTURE OVERVIEW -> {overview_path}")

    # Account mapping summary
    print(f"\n{'='*50}")
    print(f"  ACCOUNT MAPPING ({len(acc_maps)} entries)")
    print(f"{'='*50}")
    for m in sorted(acc_maps, key=lambda x: x.get("kode_transaksi_bank", "")):
        bank = m.get("bank", "ALL")
        print(f"  {m['kode_transaksi_bank']:20s} -> {m['kode_akun_erp']:12s}  {m.get('nama_akun', '')}")

    print(f"\n  Semua diagram disimpan di: {OUTPUT_DIR}")
    print(f"  File PNG bisa langsung dimasukkan ke skripsi (Bab 2 / Bab 4)")


if __name__ == "__main__":
    main()
