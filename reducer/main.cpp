// trimr-reduce: the mesh engine behind Trimr.
//   trimr-reduce reduce <in.nif> <out.nif> <ratio> <max_error> [min_tris]
//   trimr-reduce dump   <in.nif> <out.bin>          geometry + first texture path per shape (for the preview/gate)
//   trimr-reduce info   <list.txt>                  one NIF path per line; prints tab separated facts per file
// "reduce" only removes triangles. Surviving vertices keep their exact position, UV, normal, tangent and vertex colour.
// Shader, texture, alpha, collision and animation blocks are never touched. Skinned and LOD shapes are skipped.
#include "NifFile.hpp"
#include "meshoptimizer.h"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
using namespace nifly;

static bool isPlain(NiShape* s, BSTriShape*& out) {
	out = dynamic_cast<BSTriShape*>(s);
	return out && std::string(out->GetBlockName()) == "BSTriShape";
}

static int cmdDump(const char* in, const char* outp) {
	NifFile nif;
	if (nif.Load(in) != 0) return 3;
	FILE* f = fopen(outp, "wb");
	if (!f) return 4;
	for (NiShape* shape : nif.GetShapes()) {
		BSTriShape* bs;
		if (!isPlain(shape, bs)) continue;
		std::string tex;
		nif.GetTextureSlot(shape, tex, 0);
		int nv = (int)bs->vertData.size(), nt = (int)bs->triangles.size(), pl = (int)tex.size(), sk = bs->IsSkinned() ? 1 : 0;
		fwrite(&nv, 4, 1, f); fwrite(&nt, 4, 1, f); fwrite(&pl, 4, 1, f); fwrite(&sk, 4, 1, f); fwrite(tex.data(), 1, pl, f);
		for (auto& v : bs->vertData) { float p[3] = {v.vert.x, v.vert.y, v.vert.z}; fwrite(p, 4, 3, f); }
		for (auto& v : bs->vertData) { float p[2] = {v.uv.u, v.uv.v}; fwrite(p, 4, 2, f); }
		for (auto& v : bs->vertData) fwrite(v.colorData, 1, 4, f);
		for (auto& t : bs->triangles) { uint16_t p[3] = {t.p1, t.p2, t.p3}; fwrite(p, 2, 3, f); }
	}
	fclose(f);
	return 0;
}

static int cmdInfo(const char* list) {
	std::ifstream in(list);
	std::string path;
	while (std::getline(in, path)) {
		if (!path.empty() && path.back() == '\r') path.pop_back();
		if (path.empty()) continue;
		NifFile nif;
		if (nif.Load(path) != 0) { printf("INFO\t%s\t0\t0\t0\t0\t0\n", path.c_str()); continue; }
		size_t total = 0, reducible = 0; int alpha = 0, other = 0;
		for (NiShape* shape : nif.GetShapes()) {
			size_t t = shape->GetNumTriangles();
			total += t;
			BSTriShape* bs;
			if (isPlain(shape, bs) && !bs->IsSkinned()) {
				reducible += t;
				NiAlphaProperty* ap = nif.GetAlphaProperty(shape);
				if (ap && (ap->flags & 0x200)) alpha = 1;  // alpha test enabled: cut-out foliage style
			} else other++;
		}
		printf("INFO\t%s\t1\t%zu\t%zu\t%d\t%d\n", path.c_str(), total, reducible, alpha, other);
	}
	return 0;
}

static int cmdReduce(int argc, char** argv) {
	const char* in = argv[2]; const char* out = argv[3];
	float ratio = (float)atof(argv[4]), maxErr = (float)atof(argv[5]);
	size_t minTris = argc > 6 ? (size_t)atoi(argv[6]) : 300;
	NifFile nif;
	if (nif.Load(in) != 0) { printf("ERR load %s\n", in); return 3; }
	size_t totBefore = 0, totAfter = 0; int changed = 0;
	for (NiShape* shape : nif.GetShapes()) {
		BSTriShape* bs;
		if (!isPlain(shape, bs) || bs->IsSkinned()) { totBefore += shape->GetNumTriangles(); totAfter += shape->GetNumTriangles(); continue; }
		const auto& tris = bs->triangles; const auto& vd = bs->vertData;
		size_t n = vd.size(), tc = tris.size();
		totBefore += tc;
		if (tc < minTris) { totAfter += tc; continue; }
		std::vector<float> pos(n * 3), attr(n * 8);
		for (size_t i = 0; i < n; i++) {
			pos[i * 3] = vd[i].vert.x; pos[i * 3 + 1] = vd[i].vert.y; pos[i * 3 + 2] = vd[i].vert.z;
			float* a = &attr[i * 8];
			a[0] = vd[i].uv.u; a[1] = vd[i].uv.v;
			a[2] = vd[i].normal[0] / 127.5f - 1.f; a[3] = vd[i].normal[1] / 127.5f - 1.f; a[4] = vd[i].normal[2] / 127.5f - 1.f;
			a[5] = vd[i].colorData[0] / 255.f; a[6] = vd[i].colorData[1] / 255.f; a[7] = vd[i].colorData[2] / 255.f;
		}
		const float w[8] = {2.f, 2.f, 0.5f, 0.5f, 0.5f, 0.4f, 0.4f, 0.4f};  // UVs weigh most: texture placement must survive
		std::vector<unsigned int> idx(tc * 3), dst(tc * 3);
		for (size_t t = 0; t < tc; t++) { idx[t * 3] = tris[t].p1; idx[t * 3 + 1] = tris[t].p2; idx[t * 3 + 2] = tris[t].p3; }
		size_t target = (size_t)(tc * ratio) * 3; if (target < 3) target = 3;
		float err = 0.f;
		size_t got = meshopt_simplifyWithAttributes(dst.data(), idx.data(), idx.size(), pos.data(), n, sizeof(float) * 3, attr.data(), sizeof(float) * 8, w, 8, nullptr, target, maxErr, 0, &err);
		std::vector<int> remap(n, -1); std::vector<BSVertexData> nv; std::vector<Triangle> nt; nt.reserve(got / 3);
		for (size_t k = 0; k < got; k += 3) {
			uint16_t v[3];
			for (int c = 0; c < 3; c++) { unsigned int o = dst[k + c]; if (remap[o] < 0) { remap[o] = (int)nv.size(); nv.push_back(vd[o]); } v[c] = (uint16_t)remap[o]; }
			nt.emplace_back(v[0], v[1], v[2]);
		}
		bs->SetVertexData(nv); bs->SetTriangles(nt); bs->CalcDataSizes(nif.GetHeader().GetVersion());
		totAfter += nt.size(); changed++;
	}
	if (nif.Save(out) != 0) { printf("ERR save %s\n", out); return 4; }
	printf("TOTAL %zu -> %zu shapes_changed %d\n", totBefore, totAfter, changed);
	return 0;
}

int main(int argc, char** argv) {
	if (argc >= 4 && std::string(argv[1]) == "dump") return cmdDump(argv[2], argv[3]);
	if (argc >= 3 && std::string(argv[1]) == "info") return cmdInfo(argv[2]);
	if (argc >= 6 && std::string(argv[1]) == "reduce") return cmdReduce(argc, argv);
	fprintf(stderr, "usage: trimr-reduce reduce in out ratio max_error [min_tris] | dump in out.bin | info list.txt\n");
	return 2;
}
