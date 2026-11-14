"""
image-cleanup: Artifact Registry 오래된 컨테이너 이미지 자동 정리 (Cloud Run job, 주 1회)

[v1.0 / 2026-11-14] 신규
- 대상: cloud-run-source-deploy(asia-northeast3, asia-northeast1), gcr.io(us)
- 남기는 것: ① 서비스·job이 지금 쓰는 이미지(서비스는 트래픽 받는 리비전 포함)
             ② 이미지 묶음(package)별 최근 KEEP_RECENT개  ③ 'latest' 태그  ④ MIN_AGE_DAYS일 이내
- 한 묶음을 여러 job이 다른 태그로 나눠 쓰므로(mvno-bot: ktoa-collector·cafe-collector·텔레그램봇)
  AR 기본 정리 정책(최근 N개)만으로는 쓰는 이미지가 지워질 수 있어 사용 여부를 직접 확인함
- 사용 이미지 주소를 하나라도 확인 못 하면 아무것도 지우지 않고 종료
- 사용: python cleanup.py [--dry-run]
"""
import collections
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

PROJECT = "mvno-484509"
REPOS = [
    ("asia-northeast3", "cloud-run-source-deploy", f"asia-northeast3-docker.pkg.dev/{PROJECT}/cloud-run-source-deploy"),
    ("asia-northeast1", "cloud-run-source-deploy", f"asia-northeast1-docker.pkg.dev/{PROJECT}/cloud-run-source-deploy"),
    ("us", "gcr.io", f"gcr.io/{PROJECT}"),
]
RUN_REGIONS = ["asia-northeast3", "asia-northeast1"]
KEEP_RECENT = 5
MIN_AGE_DAYS = 14


def gc(args):
    r = subprocess.run(["gcloud"] + args + ["--project", PROJECT, "--format=json"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gcloud {' '.join(args[:4])} 실패: {r.stderr.strip()[-200:]}")
    return json.loads(r.stdout or "[]")


def list_versions():
    out = []
    for loc, repo, host in REPOS:
        for p in gc(["artifacts", "packages", "list", "--repository", repo, "--location", loc]):
            name = p["name"].split("/packages/")[-1]
            tags = collections.defaultdict(list)
            try:
                # gcr.io 저장소는 gcr.io/... 주소로는 태그 조회가 안 되어 AR 주소(us-docker.pkg.dev/.../gcr.io)로 조회
                tag_host = f"{loc}-docker.pkg.dev/{PROJECT}/{repo}"
                for t in gc(["artifacts", "docker", "tags", "list", f"{tag_host}/{name}"]):
                    tags[t["version"].split("/versions/")[-1]].append(t["tag"].split("/tags/")[-1])
            except RuntimeError as e:
                # 태그를 못 읽으면 'latest' 보호를 할 수 없으므로 이 묶음은 통째로 건너뜀
                print(f"⚠️ {name}: 태그 조회 실패 → 정리 제외 ({str(e)[:80]})")
                continue
            for v in gc(["artifacts", "versions", "list", "--package", name, "--repository", repo, "--location", loc]):
                dg = v["name"].split("/versions/")[-1]
                out.append(dict(loc=loc, repo=repo, host=host, pkg=name, digest=dg,
                                created=v["createTime"], tags=tags.get(dg, [])))
    return out


def resolve(ref):
    """이미지 주소(태그/다이제스트) → 다이제스트. 저장소에 없으면 ''"""
    if "@" in ref:
        return ref.split("@", 1)[1]
    if ":" not in ref.rsplit("/", 1)[-1]:
        ref += ":latest"
    r = subprocess.run(["gcloud", "artifacts", "docker", "images", "describe", ref, "--project", PROJECT,
                        "--format=value(image_summary.digest)"], capture_output=True, text=True)
    return r.stdout.strip()


def in_use_digests():
    refs, digests = set(), set()
    for region in RUN_REGIONS:
        services = gc(["run", "services", "list", "--region", region])
        serving = set()
        for s in services:
            refs.add(s["spec"]["template"]["spec"]["containers"][0]["image"])
            serving.update(t.get("revisionName") for t in s.get("status", {}).get("traffic", []))
        for rv in gc(["run", "revisions", "list", "--region", region]):
            d = rv.get("status", {}).get("imageDigest", "")
            if rv["metadata"]["name"] in serving and "@" in d:
                digests.add(d.split("@", 1)[1])
        for j in gc(["run", "jobs", "list", "--region", region]):
            refs.add(j["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]["image"])
    missing = []
    for ref in sorted(refs):
        d = resolve(ref)
        if d:
            digests.add(d)
        else:
            missing.append(ref)
    return digests, missing


def main(dry_run):
    versions = list_versions()
    inuse, missing = in_use_digests()
    # 저장소에 이미 없는 주소(예: 예전에 지워진 이미지로 돌아가는 서비스)는 지울 대상과 무관하므로 경고만
    for ref in missing:
        print(f"⚠️ 저장소에 없는 사용 이미지: {ref}")
    if not inuse:
        print("❌ 사용 중 이미지를 하나도 확인 못 함 → 중단")
        return 1

    cutoff = datetime.now(timezone.utc) - timedelta(days=MIN_AGE_DAYS)
    by_pkg = collections.defaultdict(list)
    for v in versions:
        by_pkg[(v["host"], v["pkg"])].append(v)
    targets = []
    for vs in by_pkg.values():
        vs.sort(key=lambda v: v["created"], reverse=True)
        for i, v in enumerate(vs):
            created = datetime.fromisoformat(v["created"].replace("Z", "+00:00"))
            if i < KEEP_RECENT or v["digest"] in inuse or "latest" in v["tags"] or created > cutoff:
                continue
            targets.append(v)

    print(f"이미지 {len(versions)}개 / 사용 중 {len(inuse)}개 / 정리 대상 {len(targets)}개"
          f"{' (dry-run, 삭제 안 함)' if dry_run else ''}")
    for v in targets:
        print(f"  - {v['pkg']} {v['created'][:10]} {v['digest'][:19]} {','.join(v['tags'])}")
    if dry_run:
        return 0

    fail = 0
    for v in targets:
        r = subprocess.run(["gcloud", "artifacts", "versions", "delete", v["digest"], "--package", v["pkg"],
                            "--repository", v["repo"], "--location", v["loc"], "--project", PROJECT,
                            "--delete-tags", "--quiet"], capture_output=True, text=True)
        if r.returncode != 0:
            fail += 1
            print(f"  ⚠️ 삭제 실패 {v['pkg']} {v['digest'][:19]}: {r.stderr.strip()[-150:]}")
    print(f"✅ 삭제 {len(targets) - fail}개 / 실패 {fail}개")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main("--dry-run" in sys.argv))
