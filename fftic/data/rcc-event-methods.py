# RCC version27, commit ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070.
# Original algorithms by abyssonym. Python2 print/xrange adapted.

def generate_formations(self, corner=False, numchar_override=None):
    m = MapObject.get_map(self.map_id)
    num_generic_moves = len([u for u in m.move_units if u & 0x80])
    if randint(1, num_generic_moves) > 2:
        return None
    heights = MapObject.get_certain_values_map_id(self.map_id, "height")
    depths = MapObject.get_certain_values_map_id(self.map_id, "depth")
    bads = MapObject.get_certain_values_map_id(self.map_id, "bad")
    occupieds = MapObject.get_certain_values_map_id(self.map_id,
                                                    "occupied")
    length = len(heights)
    width = len(heights[0])
    if length * width == 0:
        return None

    if numchar_override:
        num_characters = numchar_override
    else:
        num_characters = self.num_characters

    if num_characters < 2 or corner or numchar_override:
        num_formations = 1
    else:
        num_formations = random.choice([1, 1, 1, 2])

    # begin generate function
    def gen():
        winwidth = min(5, width)
        winlength = min(5, length)
        placewidth = width - 4
        placelength = length - 4
        halfwidth, halflength = placewidth/2, placelength/2
        if not corner:
            if placewidth == 0:
                x = 0
            else:
                x = randint(0, halfwidth) + randint(0, halfwidth)
                x = (x + halfwidth) % placewidth
            if placelength == 0:
                y = 0
            else:
                y = randint(0, halflength) + randint(0, halflength)
                y = (y + halflength) % placelength
        else:
            x = random.choice([0, placewidth-1])
            y = random.choice([0, placelength-1])
        assert 0 <= x <= placewidth
        assert 0 <= y <= placelength
        lines_deleted = 0
        while True:
            xmargin = min(x, width - (x+winwidth+1))
            ymargin = min(y, length - (y+winlength+1))
            if randint(0, min(xmargin, ymargin)) != 0:
                return None
            xpoints, ypoints = winwidth, winlength
            if xmargin > ymargin:
                xpoints *= 2
            elif ymargin > xmargin:
                ypoints *= 2
            value = randint(0, xpoints + ypoints)
            if value < xpoints:
                winwidth -= 1
                if x > halfwidth:
                    x += 1
            else:
                winlength -= 1
                if y > halflength:
                    y += 1

            if winwidth == 1 or winlength == 1:
                break
            if lines_deleted >= 6:
                break
            if random.choice([True, False, False, False]):
                break
        height_tolerance = 0
        while random.choice([True, False]):
            height_tolerance += 1
        try:
            winheights = slice_array_2d(heights, x, winwidth, y, winlength)
        except:
            import pdb; pdb.set_trace()
        winbads = slice_array_2d(bads, x, winwidth, y, winlength)
        windepths = slice_array_2d(depths, x, winwidth, y, winlength)
        winoccs = slice_array_2d(occupieds, x, winwidth, y, winlength)
        if [v for row in winoccs for v in row if v == 1]:
            if randint(1, 5) != 5:
                return None
        heightlist = sorted(set([h for row in winheights for h in row]))
        heightlist = [h for h in heightlist if h is not None]
        if not heightlist:
            return None
        if len(heightlist) > 1:
            heightlist = heightlist[:randint(1, len(heightlist))]
        base_height = random.choice(heightlist)
        if height_tolerance and base_height - height_tolerance <= 0:
            allow_depths = random.choice([True, False])
        else:
            allow_depths = False

        winvalid = []
        for j in range(winlength):
            winvalid.append([])
            for i in range(winwidth):
                height = winheights[j][i]
                bad = winbads[j][i]
                if height is None or bad is None:
                    winvalid[j].append(0)
                    continue
                valid = 1
                if bad:
                    valid = 0
                if not (base_height <= height <=
                        base_height + height_tolerance):
                    depth = windepths[j][i]
                    if depth == 0:
                        valid = 0
                    if height <= base_height - height_tolerance:
                        valid = 0
                    if not allow_depths:
                        valid = 0
                winvalid[j].append(valid)
        try:
            while not any(winvalid[0]):
                winvalid = winvalid[1:]
                y += 1
                winlength -= 1
            while not any(winvalid[-1]):
                winvalid = winvalid[:-1]
                winlength -= 1
            while not any(zip(*winvalid)[0]):
                winvalid = zip(*zip(*(winvalid))[1:])
                x += 1
                winwidth -= 1
            while not any(zip(*winvalid)[-1]):
                winvalid = zip(*zip(*(winvalid))[:-1])
                winwidth -= 1
        except IndexError:
            return None
        winvalid = [list(row) for row in winvalid]
        xmargin = min(x, width - (x+winwidth+1))
        ymargin = min(y, length - (y+winlength+1))
        if ((winlength > winwidth and xmargin > ymargin) or
                (winwidth > winlength and ymargin > xmargin)):
            if randint(1, 10) != 10:
                return None
        assert 0 <= x <= width - winwidth
        assert 0 <= y <= length - winlength
        if winwidth * winlength <= 2:
            return None
        return x, y, winvalid
    # end generate function

    chars = []
    if num_formations > 1:
        half = num_characters / 2
        first = randint(1, half) + randint(0, half)
        first = min(first, num_characters-1)
        chars.append(first)
        chars.append(num_characters-first)
        chars = sorted(chars, reverse=True)
        assert sum(chars) == num_characters
    else:
        chars = [num_characters]

    saved = None
    for k, subchars in enumerate(chars):
        while True:
            result = gen()
            if result is None:
                continue
            x, y, window = result
            numvalid = len([v for row in window for v in row if v])
            if (numvalid == subchars and
                    random.choice([True, True, False])):
                continue
            elif subchars <= 2 and numvalid > 12:
                continue
            if numvalid >= subchars:
                if saved is None:
                    saved = (x, y, [list(row) for row in window])
                else:
                    # collision detection
                    saved_x, saved_y, saved_window = saved
                    if abs(x - saved_x) < 5 and abs(y - saved_y) < 5:
                        continue
                    if (max(abs(x - saved_x), abs(y - saved_y)) == 5 and
                            random.choice([True, True, False])):
                        continue
                break
        for row in window:
            while len(row) < 5:
                row.append(0)
        while len(window) < 5:
            window.append([0, 0, 0, 0, 0])

        '''
        if self.entd == 0x193:
                pass
                print
                pass
                for row in window:
                    pass
                print
                import pdb; pdb.set_trace()
        '''

        for j, row in enumerate(window):
            for i, v in enumerate(row):
                if v:
                    m = MapObject.get_map(self.map_id)
                    m.set_occupied(x+i, y+j, party=True)

        bitmap = 0
        valids = [v for row in zip(*window) for v in row]
        for l, v in enumerate(valids):
            bitmap |= (v << l)
        f = FormationObject.get_unused()
        f.map_number = self.map_id
        f.bitmap = bitmap
        f.x = x + 2  # Center tile! D'oh!
        f.z = y + 2
        f.orientation = 0
        f.pick_correct_orientation()
        f.num_characters = subchars
        if k == 0:
            self.grid = f.id_number
            self.grid2 = 0
        elif k == 1:
            self.grid2 = f.id_number

    if self.grid2 and subchars > 1 and random.choice([True, False]):
        self.grid, self.grid2 = self.grid2, self.grid
    return True


def randomize_enemy_formations():
    es = [e for e in EncounterObject.every
          if e.map_id and e.entd and e.event and e.grid]

    def generate_heatmap(m, example_unit, done_units=None, upper=True):
        enemy_units = [u for u in done_units if u.get_bit("enemy_team")]
        ally_units = [u for u in done_units if u not in enemy_units]
        if not example_unit.get_bit("enemy_team"):
            enemy_units, ally_units = ally_units, enemy_units
        heatmap = [list([100 for _ in range(m.width)])
                   for _ in range(m.length)]
        for y in range(len(heatmap)):
            for x in range(len(heatmap[0])):
                if m.get_tile_value(x, y, "bad"):
                    if (m.get_tile_value(x, y, "unreachable") or
                            m.get_tile_value(x, y, "bad_regardless") or
                            example_unit.x != x or example_unit.y != y):
                        heatmap[y][x] = -999999999
                        continue
                for u in done_units:
                    if u.x == x and u.y == y:
                        heatmap[y][x] = -999999999
                        break
                    if u.x == x:
                        heatmap[y][x] -= 10
                    if u.y == y:
                        heatmap[y][x] -= 10
                if heatmap[y][x] <= -99999999:
                    continue
                if x == 0 or x == len(heatmap[0])-1:
                    heatmap[y][x] -= 5
                elif y == 0 or y == len(heatmap)-1:
                    heatmap[y][x] -= 5
                for i in range(-9, 10):
                    for j in range(-9, 10):
                        if min(x+i, y+j) < 0:
                            continue
                        dist = abs(i) + abs(j)
                        if dist > 9:
                            continue
                        if dist <= 2:
                            for u in enemy_units:
                                if u.x == x+i and u.y == y+j:
                                    heatmap[y][x] -= (16 / max(dist, 1))
                        if dist >= 4:
                            for u in enemy_units:
                                if u.x == x+i and u.y == y+j:
                                    heatmap[y][x] += max(10 - dist, 0)
                        try:
                            party = m.get_tile_value(x+i, y+j, "party")
                            if party:
                                distval = max(10 - dist, 0)
                                if example_unit.get_bit("enemy_team"):
                                    heatmap[y][x] -= int(round(distval ** 1.5))
                                elif distval < 7:
                                    heatmap[y][x] += distval / 2
                        except IndexError:
                            pass
        values = sorted(set([v for row in heatmap for v in row]))
        values = dict([(k, v) for (v, k) in enumerate(values)])
        valids = sorted(values.values())
        valids = valids[randint(0, len(valids)-1):]
        if random.choice([True, False]):
            valids = valids[randint(0, len(valids)-1):]
        candidates = []
        for y, row in enumerate(heatmap):
            for x, v in enumerate(row):
                heatmap[y][x] = values[heatmap[y][x]]
                if heatmap[y][x] in valids:
                    candidates.append((x, y))
        x, y = random.choice(candidates)
        example_unit.x, example_unit.y = x, y
        example_unit.fix_facing(m)
        example_unit.facing &= 0x7F
        if upper and m.get_tile_value(x, y, "upper"):
            if random.choice([True, True, True, False]):
                example_unit.facing |= 0x80
        return heatmap

    set_progress_counter(len(es))
    for n, e in enumerate(es):
        check_progress_counter(n)
        m = MapObject.get_map(e.map_id)
        if not any(m.get_tile_values("party")):
            continue
        if e.mutated:
            units = m.units
        else:
            units = m.nonmoving_units
        random.shuffle(units)
        for i in range(len(units)):
            ex = units[i]
            done = units[:i]
            generate_heatmap(m, ex, done, upper=not e.mutated)

        new_units = []
        rogue = False
        while True:
            unused = list(m.unused_units)
            threshold = int(60 * ((0.5*boostd['difficulty_factor'])
                                  ** len(new_units)))
            threshold = min(threshold, 60)
            value = randint(1, 100)
            if len(unused) < 6 or value > threshold:
                break
            new = max(unused, key=lambda u: u.index)
            used = (m.nonmoving_units +
                    [u for u in m.moving_units if u.graphic & 0x80])
            used = sorted(set(used), key=lambda u: u.index)
            used = [u for u in used if not u.is_lucavi and u.level != 1]
            temp = [u for u in used
                    if u.job not in [u2.job for u2 in new_units]]
            if temp and random.choice([True, True, False]):
                used = temp
            if not used:
                break
            used = [u for u in used if not u.has_special_graphic]
            if not used:
                continue
            old = random.choice(used)
            new.copy_data(old)
            new.mutate(preserve_job=True)
            new.unlocked_level = old.unlocked_level
            new_enemies = [u for u in new_units if u.get_bit("enemy_team")]
            new.set_bit("randomly_present", False)
            new.set_bit("always_present", True)
            new.set_bit("join_after_event", False)
            new.set_bit("enemy_team", True)
            assert not new.has_special_graphic
            new.unit_id = 0x80 | (new.index & 0xF)
            new.name = 0xFF
            if not rogue:
                if boostd["difficulty_factor"] > 1.0:
                    chance = max(7-len(new_enemies), 1)
                else:
                    chance = max(5-(2*len(new_enemies)), 1)
                if randint(1, chance) == 1:
                    new.set_bit("enemy_team", False)
                    if (not new.has_special_graphic and
                            random.choice([True, True, False])):
                        new.set_bit("join_after_event", True)
                    rogue = True
                if (boostd["difficulty_factor"] > 1.0
                        or new.get_bit("enemy_team")):
                    if randint(1, 10) == 10:
                        new.set_bit("alternate_team", True)
                        rogue = True
            while True:
                generate_heatmap(m, new, units+new_units, upper=not e.mutated)
                for u in m.units:
                    if u != new and u.x == new.x and u.y == new.y:
                        break
                else:
                    break
            new_units.append(new)



def mutate_units_special():
    pass
    generate_balmafula()
    ranked_jobs = get_ranked("job")
    special_jobs = [j for j in get_jobs() if not 5 <= j.skillset <= 0x18
                    and not j.skillset == 0
                    and not 0x4A <= j.index <= 0x8F
                    and not j.index >= 0x92]
    for j in list(special_jobs):
        for u in UnitObject.every:
            if u.job == j.index and 1 <= u.graphic <= 0x7F:
                break
        else:
            special_jobs.remove(j)
    special_jobs = [j.index for j in special_jobs]
    special_jobs = [j for j in ranked_jobs if j in special_jobs]
    backup_special_jobs = list(special_jobs)
    for map_id in range(1, 0xFE) + range(0x180, 0x1D5):
        if map_id <= 0xFF:
            boost_factor = boostd["random_special_unit"]
        else:
            boost_factor = boostd["story_special_unit"]

        lucavi_special = False
        units = sorted(mapunits[map_id], key=lambda u: u.index)
        if any([u.is_lucavi for u in units]):
            if map_id == 0x1a9:
                continue
            lucavi_special = (any([u.is_altima for u in units])
                              or any([u.job == 0x97 for u in units])
                              or randint(1, 3) != 3)
            lucavi_unit = max([u for u in units if u.is_lucavi],
                              key=lambda u2: u2.level)
        elif map_id == 1:
            probval = 5
        elif map_id == 0x180:
            probval = 12
            special_jobs = list(backup_special_jobs)
        else:
            probval -= 1
            probval = max(probval, 2)

        if map_id in [0x183, 0x184, 0x185]:
            continue
        if lucavi_special or randint(1, probval) == 1:
            if map_id == 0x192:
                candidates = [u for u in units if u.graphic == 0x82
                              and u.job != 0x97 and u.get_bit("enemy_team")]
            else:
                candidates = [u for u in units if 0x80 <= u.graphic <= 0x82]
                noncandidates = [u for u in units if u not in candidates]
                noncandjobs = [u.job for u in noncandidates
                               if 0x80 <= u.graphic <= 0x82]
                candidates = [c for c in candidates
                              if c.job not in noncandjobs]

            for c in list(candidates):
                if c.named or not c.get_bit("enemy_team"):
                    if 0x5E <= c.job <= 0x8D or c.graphic == 0x82:
                        candidates = [d for d in candidates if
                                      d.monster_portrait != c.monster_portrait]
                    elif c.graphic in [0x80, 0x81]:
                        candidates = [d for d in candidates
                                      if d.job != c.job]
                    assert c not in candidates

            if not candidates:
                continue
            jobs = [c.job for c in candidates]
            jobs = [get_job(j).monster_portrait | 0x100 if 0x5E <= j <= 0x8D
                    else j for j in jobs]
            jobs = [j for j in jobs if (j & 0xFF) > 0]
            jobs = Counter(jobs)
            if len(jobs.keys()) == 1 and not lucavi_special:
                continue

            jobs = [key for key in jobs if jobs[key] == min(jobs.values())]
            replace_job = random.choice(sorted(jobs))
            if replace_job >= 0x100:
                replace_job &= 0xFF
                replace_job = [c.job for c in candidates if
                               c.monster_portrait == replace_job]
                replace_job = sorted(replace_job)[0]

            cand_jobs = [j for j in ranked_jobs
                         if j in special_jobs or j == replace_job
                         or (lucavi_special and j == lucavi_unit.job)]
            if map_id in [0x10d, 0x190, 0x1a8, 0x1b0]:
                cand_jobs = [j for j in cand_jobs
                             if JobObject.get(j).guaranteed_female
                             or j == replace_job
                             or (lucavi_special and j == lucavi_unit.job)]
            if map_id >= 0x180:
                cand_jobs = [j for j in cand_jobs if j > 3]
            index = cand_jobs.index(replace_job)
            if lucavi_special:
                lucorder_index = LUCAVI_ORDER.index(lucavi_unit.job)
                badlucs = LUCAVI_ORDER[lucorder_index:]
                cand_jobs = [c for c in cand_jobs if
                             c == lucavi_unit.job or c not in badlucs]
                lucavi_index = cand_jobs.index(lucavi_unit.job)
                index = (index + lucavi_index) / 2
                if lucavi_unit.job in cand_jobs and randint(1, 10) != 10:
                    cand_jobs.remove(lucavi_unit.job)
            index = randint(index, int(round(index * boost_factor)))
            cand_jobs.remove(replace_job)
            if len(cand_jobs) >= 7:
                index = min(index, len(cand_jobs)-4)
                index = max(index, 3)
            index = min(index, len(cand_jobs)-1)
            index = mutate_normal(index, minimum=0, maximum=len(cand_jobs)-1)
            new_job = cand_jobs[index]

            jobunits = [u for u in get_units() if u.job == new_job
                        and u.map_id in USED_MAPS]
            jobgraphics = Counter([u.graphic for u in jobunits])
            jobgraphics = [key for key in jobgraphics
                           if jobgraphics[key] == max(jobgraphics.values())]
            if not jobunits or not jobgraphics:
                continue
            graphic = random.choice(sorted(jobgraphics))
            jobunits = [u for u in jobunits if u.graphic == graphic]

            def jobunit_filter(strength):
                candidates = []
                for u in jobunits:
                    score = 0
                    if u.get_bit("join_after_event"):
                        score += 1
                    for field in ["secondary", "lefthand", "righthand", "head",
                                  "body", "accessory", "reaction", "support",
                                  "movement"]:
                        value = getattr(u, field) & 0xFF
                        if 1 <= value <= 0xFD:
                            score += 1
                    if score > strength:
                        candidates.append(u)
                return candidates

            threshold = randint(0, 5) + randint(0, 5)
            while True:
                tempunits = jobunit_filter(threshold)
                if tempunits:
                    break
                threshold -= 1

            jobunits = tempunits
            chosen_unit = random.choice(sorted(jobunits,
                                               key=lambda u: u.index))

            if not 0x5E <= replace_job:
                change_units = [u for u in units if u.job == replace_job]
                if any([u.graphic == chosen_unit.graphic
                        and not u.get_bit("enemy_team") for u in units]):
                    continue
            else:
                mg = get_job(replace_job).monster_portrait
                assert mg > 0
                change_units = [u for u in units
                                if u.monster_portrait == mg]

            change_units = [u for u in change_units if u.graphic > 0]
            change_units = sorted(change_units, key=lambda u: u.index)
            old_job = change_units[0].job
            alternate_team = not lucavi_special and randint(1, 25) == 25
            for unit in change_units:
                if map_id == 0x192 and not unit.get_bit("enemy_team"):
                    continue
                try:
                    assert not any([unit.named, unit.has_special_graphic,
                                    not unit.get_bit("enemy_team")])
                except:
                    raise Exception("Invalid unit replacement.")

                unit.job = chosen_unit.job
                unit.graphic = chosen_unit.graphic
                for bitname in ["monster", "female", "male", "hidden_stats"]:
                    unit.set_bit(bitname, chosen_unit.get_bit(bitname))
                copy_attrs = ["job", "graphic", "month", "day", "trophy",
                              "gil", "brave", "faith", "palette", "secondary",
                              "reaction", "support", "movement", "unlocked",
                              "unlocked_level"]
                for attr in copy_attrs:
                    setattr(unit, attr, getattr(chosen_unit, attr))
                if lucavi_special:
                    for attr in ["lefthand", "righthand", "head", "body",
                                 "accessory", "secondary"]:
                        chosenvalue = getattr(chosen_unit, attr)
                        oldvalue = getattr(unit, attr)
                        if (1 <= chosenvalue <= 0xFE and
                                random.choice([True, False])):
                            setattr(unit, attr, chosenvalue)
                        elif oldvalue in [0, 0xFF]:
                            setattr(unit, attr, 0xFE)
                    for attr in ["reaction", "support", "movement"]:
                        chosenvalue = getattr(chosen_unit, attr)
                        oldvalue = getattr(unit, attr)
                        if (1 <= chosenvalue <= 0x1FE
                                and random.choice([True, False])):
                            setattr(unit, attr, chosenvalue)
                        elif oldvalue in [0, 0x1FF]:
                            setattr(unit, attr, 0x1FE)
                elif alternate_team or randint(1, 10) == 10:
                    unit.set_bit("alternate_team", True)
                for method in ["mutate_equips", "mutate_rsm",
                               "mutate_secondary", "mutate_level"]:
                    if random.choice([True, False]):
                        getattr(unit, method)()
                unit.set_bit("enemy_team", True)
                if chosen_unit.named:
                    unit.name = chosen_unit.name
                SUPER_SPECIAL.append(unit)

            job = get_job(chosen_unit.job)
            if (not job.can_invite and
                    random.choice([True, False, False])):
                unit = random.choice(change_units)
                unit.set_bit("join_after_event", True)

            similar_graphic_jobs = [u.job for u in UnitObject.every
                                    if u.graphic == chosen_unit.graphic]
            special_jobs = [j for j in special_jobs
                            if j not in similar_graphic_jobs]
            if not special_jobs:
                special_jobs = list(backup_special_jobs)

            if map_id >= 0x180:
                if not lucavi_special:
                    probval = max(probval, 12)
            else:
                probval = max(probval, 5)



def generate_balmafula():
    arc_witch = JobObject.get(0x21)
    arc_witch.skillset = 0x7C
    for attr in ["hpgrowth", "hpmult", "mpgrowth", "mpmult", "spdgrowth",
                 "spdmult", "pagrowth", "pamult", "magrowth", "mamult",
                 "move", "jump", "evade"]:
        index = randint(0x4A, 0x5E)
        setattr(arc_witch, attr, getattr(JobObject.get(index), attr))


