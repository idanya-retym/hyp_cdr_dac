import numpy as np
import noise_freq_reduce_v1_7 as m

f0, v0 = m.load_csv(m.INPUT_FILE)
f, x, y, p = m.build_axes(f0, v0)
pk = m.detect_spurs(f, p)
ex = m.load_freq_list(m.EXISTING_FREQ_FILE)
exin = ex[(ex >= f[0]) & (ex <= f[-1])]
em = np.zeros(f.size, bool)
em[m.nearest_indices(f, exin)] = True

for nb, merge, t in [(1, True, 2), (1, True, 5), (0, True, 2), (0, True, 5),
                     (0, False, 2), (0, False, 5)]:
    sp = np.zeros(f.size, bool)
    for k in range(-nb, nb + 1):
        sp[np.clip(pk + k, 0, f.size - 1)] = True
    force = sp | em if merge else sp
    keep = m.area_reduce(f, p, t, force=force)
    keep[0] = keep[-1] = True
    e = m.integrated_noise_error(f, p, keep)[2]
    miss = int(np.sum(m.spur_errors_db(f, p, keep, pk) < -3))
    print(f"neighbors={nb} merge={merge!s:5} target={t:>2}% -> {int(keep.sum()):5d} pts"
          f"  err={e:+.2f}%  missed={miss}", flush=True)
