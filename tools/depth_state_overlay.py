"""Preserve D3D9's disabled depth-buffer semantics in the WebGPU pipeline.

Anchored to the pinned MIT-licensed th0mk/nfsu2-web encoder. See
patches/nfsu2-web.LICENSE. D3DRS_ZENABLE=FALSE disables depth writes even
when the independent ZWRITEENABLE state is still TRUE. A depth-disabled
offscreen pass must also leave the bound persistent depth surface intact.
"""


def encoder(source):
    old = "depthWriteEnabled: (dm & 2) !== 0, depthCompare:"
    new = "depthWriteEnabled: (dm & 3) === 3, depthCompare:"
    if source.count(old) != 1:
        raise ValueError("expected one pinned WebGPU depth-write descriptor")
    source = source.replace(old, new, 1)
    old = "} else { z = undefined; this.zMismatch++; }"
    new = """} else {
            if (this.zMismatch < 8) this.log(`[gpu] depth size mismatch: zid=${zid} depth=${z.width}x${z.height} target=${w}x${h} targetId=${target}; depth disabled for this pass`);
            z = undefined; this.zMismatch++;
          }"""
    if source.count(old) != 1:
        raise ValueError("expected one pinned WebGPU depth size mismatch branch")
    source = source.replace(old, new, 1)
    changes = [
        ("let curT = -1, curZ = -1, realZ = false, passKey = -2, passCube = -1;",
         "let curT = -1, curZ = -1, realZ = false, passNeedsDepth = false, passKey = -2, passCube = -1;"),
        ("const openPass = (target: number, zid: number): GPURenderPassEncoder | null => {",
         "const openPass = (target: number, zid: number, depthNeeded: boolean): GPURenderPassEncoder | null => {\n"
         "      passNeedsDepth = depthNeeded;"),
        ("      if (zid && zid < 64) {",
         "      // Z-disabled effects must not resize or clear the bound scene depth.\n"
         "      if (depthNeeded && zid && zid < 64) {"),
        ("      const zsplit = zid !== curZ && !(pass && kind !== Kind.Clear && (depth & 3) === 0);\n"
         "      if (curT === -1 || target !== curT || zsplit) {",
         "      const needsDepth = kind === Kind.Clear ? (u32[w + D.clrFlags] & 2) !== 0 : (depth & 1) !== 0;\n"
         "      const zsplit = zid !== curZ && !(pass && kind !== Kind.Clear && !needsDepth);\n"
         "      // A pass opened with scratch depth must acquire the real surface\n"
         "      // before a later depth-enabled draw on the same colour target.\n"
         "      if (curT === -1 || target !== curT || zsplit || (needsDepth && !passNeedsDepth)) {"),
        ("        pass = openPass(target, zid);", "        pass = openPass(target, zid, needsDepth);"),
    ]
    for old, new in changes:
        if source.count(old) != 1:
            raise ValueError(f"expected one pinned depth-pass anchor: {old[:70]}")
        source = source.replace(old, new, 1)
    return source
