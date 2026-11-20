"""Тести «мозку» бадді: голод, свята, слова, прогрес, нагадування, стан комп'ютера."""

import datetime as dt
import json
import random
import subprocess
import tempfile
import time
import unittest
import wave
from pathlib import Path

import buddy_hook
import claude_link
import gitwatch
import lesson
import progress
import reminders
import skins
import sounds
import sysinfo
import tamagotchi
import words


class TamagotchiTest(unittest.TestCase):
    def test_decay_over_time(self):
        needs = tamagotchi.Needs(80, 80, updated=1000.0)
        needs.decay(now=1000.0 + 6 * 3600)  # 6 годин: ситість -60, настрій -40
        self.assertAlmostEqual(needs.satiety, 20)
        self.assertAlmostEqual(needs.mood, 40)
        self.assertTrue(needs.hungry)

    def test_never_below_zero_and_clock_back(self):
        needs = tamagotchi.Needs(10, 10, updated=1000.0)
        needs.decay(now=1000.0 + 10 ** 7)
        self.assertEqual((needs.satiety, needs.mood), (0, 0))
        needs.decay(now=0)  # годинник перевели назад — нічого не ламається
        self.assertEqual(needs.satiety, 0)

    def test_feed_refuses_when_full(self):
        needs = tamagotchi.Needs(96, 50, updated=time.time())
        self.assertFalse(needs.feed())
        needs.satiety = 50
        self.assertTrue(needs.feed())
        self.assertAlmostEqual(needs.satiety, 75, delta=0.1)


class SeasonsTest(unittest.TestCase):
    def season(self, iso, birthday=None):
        s = skins.active_season(dt.date.fromisoformat(iso), birthday)
        return s.name if s else None

    def test_orthodox_easter(self):
        self.assertEqual(skins.orthodox_easter(2025), dt.date(2025, 4, 20))
        self.assertEqual(skins.orthodox_easter(2026), dt.date(2026, 4, 12))
        self.assertEqual(skins.orthodox_easter(2027), dt.date(2027, 5, 2))

    def test_vyshyvanka_day_is_third_thursday_of_may(self):
        day = skins.vyshyvanka_day(2026)
        self.assertEqual((day.month, day.weekday()), (5, 3))
        self.assertTrue(15 <= day.day <= 21)

    def test_holidays(self):
        self.assertTrue(self.season("2026-12-25").startswith("Різдво"))
        self.assertTrue(self.season("2026-12-31").startswith("Новорічний"))
        self.assertTrue(self.season("2027-01-10").startswith("Новорічний"))  # через Новий рік
        self.assertTrue(self.season("2026-04-12").startswith("Великдень"))
        self.assertTrue(self.season("2026-10-31").startswith("Хелловін"))
        self.assertIsNone(self.season("2026-11-20"))

    def test_birthday_wins_and_feb_29(self):
        self.assertIn("день народження", self.season("2026-12-25", (12, 25)))
        self.assertIn("день народження", self.season("2027-02-28", (2, 29)))  # невисокосний рік
        self.assertEqual(skins.parse_birthday("02-29"), (2, 29))
        self.assertIsNone(skins.parse_birthday("13-40"))
        self.assertIsNone(skins.parse_birthday(None))

    def test_locked_skins_exist_and_match_achievements(self):
        for slot, items in skins.LOCKED.items():
            for acc_id, achievement in items.items():
                self.assertIn(acc_id, skins.SLOTS[slot][1])
                self.assertIn(achievement, progress.BY_ID)


class WordsTest(unittest.TestCase):
    day = dt.date(2026, 11, 20)

    def test_every_word_has_a_known_topic_and_no_duplicates(self):
        self.assertEqual(len(words.BY_EN), len(words.WORDS))
        for w in words.WORDS:
            self.assertIn(w.topic, words.TOPICS)

    def test_pool_by_topic(self):
        it = words.pool({"it": True})
        self.assertTrue(it and all(w.topic == "it" for w in it))
        self.assertEqual(len(words.pool({})), len(words.WORDS))  # нічого не вибрано — усі

    def test_leitner_boxes(self):
        book, word = {}, words.WORDS[0]
        words.review(book, word, True, self.day)
        self.assertEqual(words.box(book, word), 1)
        self.assertEqual(words.due(book, word), self.day + dt.timedelta(days=1))
        for _ in range(3):
            words.review(book, word, True, self.day)
        self.assertGreaterEqual(words.box(book, word), words.KNOWN_BOX)
        self.assertEqual(words.known_count(book), 1)
        words.review(book, word, False, self.day)  # помилка — назад у нульову коробку
        self.assertEqual(words.box(book, word), 0)
        self.assertEqual(book[word.en]["wrong"], 1)

    def test_quiz_has_four_different_options_with_the_answer(self):
        for seed in range(30):
            q = words.random_question(words.pool({"food": True}), {}, self.day, random.Random(seed))
            self.assertEqual(len(set(q.options)), 4)
            self.assertIn(q.correct, q.options)

    def test_quiz_prefers_mistakes(self):
        pool = words.WORDS[:5]
        book = {}
        for w in pool:  # усі вивчені й не потребують повторення, крім одного
            for _ in range(5):
                words.review(book, w, True, self.day)
        words.review(book, pool[2], False, self.day)
        picks = {words.pick_quiz_word(pool, book, self.day, random.Random(s)).en for s in range(20)}
        self.assertEqual(picks, {pool[2].en})

    def test_word_of_day_skips_known_words(self):
        pool = words.WORDS[:3]
        book = {}
        for _ in range(5):
            words.review(book, pool[0], True, self.day)
            words.review(book, pool[1], True, self.day)
        self.assertEqual(words.word_of_day(self.day, pool, book), pool[2])


class ProgressTest(unittest.TestCase):
    def tracker(self):
        return progress.Tracker(progress.Progress(), autosave=False)

    def test_levels(self):
        self.assertEqual(progress.level_for(0), 1)
        self.assertEqual(progress.level_for(24), 1)
        self.assertEqual(progress.level_for(25), 2)
        self.assertEqual(progress.level_for(400), 5)
        for level in range(1, 10):
            self.assertEqual(progress.level_for(progress.xp_for(level)), level)

    def test_xp_level_up_and_achievement(self):
        t = self.tracker()
        gains = t.add("pomodoro", day=dt.date(2026, 1, 1))
        self.assertEqual(gains.xp, 20)
        self.assertEqual([a.id for a in gains.unlocked], ["first_pomo"])
        gains = t.add("pomodoro", day=dt.date(2026, 1, 1))
        self.assertEqual(gains.level_up, 2)  # 40 XP
        self.assertEqual(t.p.today(dt.date(2026, 1, 1))["pomodoro"], 2)

    def test_achievement_unlocks_once(self):
        t = self.tracker()
        self.assertTrue(t.add("claude").unlocked)
        self.assertFalse(t.add("claude").unlocked)

    def test_day_streak(self):
        t = self.tracker()
        for day in (1, 2, 3):
            t.add("pet", day=dt.date(2026, 3, day))
        self.assertEqual(t.p.day_streak, 3)
        t.add("pet", day=dt.date(2026, 3, 10))  # пропустив кілька днів
        self.assertEqual(t.p.day_streak, 1)

    def test_quiz_streak_and_reward(self):
        t = self.tracker()
        unlocked = []
        for w in words.WORDS[:5]:
            unlocked += t.quiz_answer(w, True).unlocked
        self.assertIn("quiz_streak_5", [a.id for a in unlocked])
        t.quiz_answer(words.WORDS[6], False)
        self.assertEqual(t.p.quiz_streak, 0)
        self.assertEqual(t.p.best["quiz_streak"], 5)

    def test_save_and_load(self):
        t = progress.Tracker(progress.Progress())
        t.add("feed")
        t.quiz_answer(words.WORDS[0], True)
        loaded = progress.load()
        self.assertEqual(loaded.totals["feed"], 1)
        self.assertIn(words.WORDS[0].en, loaded.word_book)

    def test_word_of_day_is_stable_during_the_day(self):
        t = self.tracker()
        day = dt.date(2026, 5, 5)
        first = t.word_of_day(day, words.WORDS)
        for _ in range(5):  # вивчив це слово — але слово дня до кінця дня те саме
            words.review(t.p.word_book, first, True, day)
        self.assertEqual(t.word_of_day(day, words.WORDS), first)


class ClaudeLinkTest(unittest.TestCase):
    def test_describe_tool(self):
        self.assertEqual(claude_link.describe_tool("Bash", "python3 -m unittest"), "Запускаю тести 🧪")
        self.assertEqual(claude_link.describe_tool("Bash", "git commit -m x"), "Комічу 💾")
        self.assertEqual(claude_link.describe_tool("Bash", "git push origin main"), "Відправляю на GitHub 🚀")
        self.assertEqual(claude_link.describe_tool("Bash", "npm run build"), "Збираю проєкт 🔨")
        self.assertIsNone(claude_link.describe_tool("Bash", "ls -la"))
        self.assertEqual(claude_link.describe_tool("Edit", "/a/b/buddy.py"), "Редагую buddy.py ✏️")
        self.assertIsNone(claude_link.describe_tool("Read", "/a/b"))

    def test_tool_detail_keeps_only_what_is_needed(self):
        self.assertEqual(claude_link.tool_detail("Write", {"file_path": "/x/y.txt", "content": "secret"}),
                         "/x/y.txt")
        self.assertEqual(claude_link.tool_detail("Bash", {"command": "ls"}), "ls")
        self.assertEqual(claude_link.tool_detail("Bash", None), "")


class HookInstallTest(unittest.TestCase):
    def test_install_is_idempotent_and_keeps_other_hooks(self):
        other = {"type": "command", "command": "echo mine"}
        settings = {"model": "opus", "hooks": {"Stop": [{"hooks": [other]}]}}
        once = buddy_hook.install(json.loads(json.dumps(settings)))
        twice = buddy_hook.install(json.loads(json.dumps(once)))
        self.assertEqual(once, twice)
        commands = json.dumps(twice["hooks"]["Stop"])
        self.assertIn("echo mine", commands)
        self.assertEqual(commands.count(buddy_hook.MARK), 1)
        self.assertEqual(twice["hooks"]["PreToolUse"][0]["matcher"], "Bash|Edit|MultiEdit|Write|NotebookEdit")

    def test_uninstall_removes_only_ours(self):
        other = {"type": "command", "command": "echo mine"}
        settings = buddy_hook.install({"hooks": {"Stop": [{"hooks": [other]}]}})
        cleaned = buddy_hook.uninstall(settings)
        self.assertEqual(cleaned["hooks"], {"Stop": [{"hooks": [other]}]})
        self.assertNotIn("hooks", buddy_hook.uninstall(buddy_hook.install({})))

    def test_update_settings_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps({"theme": "dark"}))
            buddy_hook.update_settings(buddy_hook.install, path)
            data = json.loads(path.read_text())
            self.assertEqual(data["theme"], "dark")
            self.assertIn("Notification", data["hooks"])


class RemindersTest(unittest.TestCase):
    def test_next_time(self):
        now = dt.datetime(2026, 11, 20, 14, 30)
        self.assertEqual(reminders.next_time(15, 0, now), dt.datetime(2026, 11, 20, 15, 0))
        self.assertEqual(reminders.next_time(9, 0, now), dt.datetime(2026, 11, 21, 9, 0))  # завтра

    def test_split_and_persist(self):
        items = [reminders.Reminder("later", 200.0), reminders.Reminder("now", 100.0)]
        due, waiting = reminders.split_due(items, 150.0)
        self.assertEqual([r.text for r in due], ["now"])
        self.assertEqual([r.text for r in waiting], ["later"])
        reminders.save(items)
        self.assertEqual([r.text for r in reminders.load()], ["now", "later"])  # за часом


class SysinfoTest(unittest.TestCase):
    def test_parse_cpu_times(self):
        idle, total = sysinfo.parse_cpu_times("cpu  100 0 50 800 50 0 0 0 0 0\ncpu0 1 2 3 4")
        self.assertEqual((idle, total), (850, 1000))

    def test_parse_meminfo(self):
        text = "MemTotal:       1000 kB\nMemFree:  100 kB\nMemAvailable:    250 kB\n"
        self.assertAlmostEqual(sysinfo.parse_meminfo(text), 75.0)
        self.assertIsNone(sysinfo.parse_meminfo("nothing here"))

    def test_cpu_temp_from_fake_sysfs(self):
        with tempfile.TemporaryDirectory() as folder:
            dev = Path(folder) / "hwmon1"
            dev.mkdir()
            (dev / "name").write_text("coretemp\n")
            (dev / "temp2_input").write_text("50000\n")
            (dev / "temp2_label").write_text("Core 0\n")
            (dev / "temp1_input").write_text("61000\n")
            (dev / "temp1_label").write_text("Package id 0\n")
            self.assertEqual(sysinfo.cpu_temp(Path(folder)), 61.0)
            self.assertIsNone(sysinfo.cpu_temp(Path(folder) / "missing"))


class GitWatchTest(unittest.TestCase):
    def test_parse_status(self):
        out = " M a.py\0?? new.txt\0R  new_name.py\0old_name.py\0 D gone.py\0"
        self.assertEqual(gitwatch.parse_status(out),
                         [(" M", "a.py"), ("??", "new.txt"), ("R ", "new_name.py"), (" D", "gone.py")])

    def test_stale_repo_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder) / "proj"
            repo.mkdir()
            run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
            run("init", "-q")
            self.assertEqual(gitwatch.find_repos([Path(folder)]), [repo])
            self.assertIsNone(gitwatch.uncommitted_since(repo))  # порожній і чистий
            (repo / "notes.txt").write_text("hi")
            since = gitwatch.uncommitted_since(repo)
            self.assertIsNotNone(since)
            self.assertEqual(gitwatch.stale_repos([Path(folder)], since + 10, 3600), [])
            stale = gitwatch.stale_repos([Path(folder)], since + 7200, 3600)
            self.assertEqual([r for r, _age in stale], [repo])


class SoundsTest(unittest.TestCase):
    def test_wav_files_are_valid(self):
        with tempfile.TemporaryDirectory() as folder:
            player = sounds.Player(Path(folder))
            player.prepare()
            for name in sounds.MELODIES:
                with wave.open(str(player.path(name))) as f:
                    self.assertEqual(f.getframerate(), sounds.RATE)
                    self.assertGreater(f.getnframes(), 1000)

    def test_samples_fit_16_bit(self):
        data = sounds.samples([(440, 0.05), (0, 0.01)])
        self.assertTrue(all(-32768 <= v <= 32767 for v in data))
        self.assertEqual(data[-1], 0)  # пауза — тиша


class LessonTest(unittest.TestCase):
    today = dt.date(2026, 11, 20)
    goal = dt.date(2027, 5, 31)

    def test_daily_target_spreads_words_until_goal(self):
        days = lesson.days_for_new_words(self.today, self.goal)
        self.assertEqual(days, 179)  # 193 дні мінус два тижні на повторення
        self.assertEqual(lesson.daily_target(1600, self.today, self.goal), 9)  # 1600 / 179 -> 9
        self.assertEqual(lesson.daily_target(0, self.today, self.goal), 0)
        self.assertEqual(lesson.daily_target(2, self.today, self.goal), 2)  # не більше, ніж лишилось
        self.assertEqual(lesson.daily_target(10, self.today, self.goal), lesson.MIN_NEW)
        late = dt.date(2027, 5, 25)  # уже після «буфера» — по максимуму
        self.assertEqual(lesson.daily_target(500, late, self.goal), lesson.MAX_NEW)

    def test_plan_is_fixed_for_the_day(self):
        pool, book = words.WORDS, {}
        plan, state = lesson.today_plan({}, book, pool, self.today, self.goal)
        self.assertEqual([w.en for w in plan.new], [w.en for w in pool[:len(plan.new)]])  # від простих
        for w in plan.new:  # познайомився з усіма — план на сьогодні той самий
            words.mark_seen(book, w, self.today)
        again, state2 = lesson.today_plan(state, book, pool, self.today, self.goal)
        self.assertEqual([w.en for w in again.new], [w.en for w in plan.new])
        self.assertEqual(state, state2)
        tomorrow, _ = lesson.today_plan(state2, book, pool, self.today + dt.timedelta(days=1), self.goal)
        self.assertFalse(set(w.en for w in tomorrow.new) & set(w.en for w in plan.new))  # завтра нові
        self.assertTrue(tomorrow.reviews)  # а вчорашні — на повторення

    def test_add_extra(self):
        pool, book = words.WORDS, {}
        _plan, state = lesson.today_plan({}, book, pool, self.today, self.goal)
        before = list(state["new"])
        extra = lesson.add_extra(state, book, pool, 5)
        self.assertEqual(len(extra), 5)
        self.assertEqual(state["new"][:len(before)], before)
        self.assertFalse(set(before) & {w.en for w in extra})

    def test_mark_known_and_due_words(self):
        book = {}
        a, b = words.WORDS[0], words.WORDS[1]
        words.mark_known(book, a, self.today)
        words.mark_seen(book, b, self.today - dt.timedelta(days=3))  # пора повторити
        self.assertEqual(words.box(book, a), words.KNOWN_BOX)
        self.assertEqual(words.due_words([a, b], book, self.today), [b])

    def test_question_in_both_directions(self):
        rng = random.Random(1)
        word = words.WORDS[3]
        q = words.make_question(word, words.WORDS, rng, "uk")
        self.assertEqual((q.prompt, q.correct), (word.uk, word.en))
        self.assertEqual(len(set(q.options)), 4)
        self.assertIn(word.en, q.options)

    def test_same_translation_is_never_a_wrong_option(self):
        offer = words.Word("offer", "пропонувати", "x", "х", "verbs", "B1")
        suggest = words.Word("suggest", "пропонувати", "x", "х", "verbs", "B1")
        pool = [offer, suggest, *words.WORDS[:20]]
        for seed in range(20):
            q = words.make_question(offer, pool, random.Random(seed), "uk")
            self.assertNotIn("suggest", q.options)

    def test_load_words_skips_broken_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "w.tsv"
            path.write_text("cat\tкіт\tA cat.\tКіт.\tgeneral\tA1\n"
                            "broken line\n"
                            "cat\tкішка\tDup.\tПовтор.\tgeneral\tA1\n"
                            "dog\tпес\tA dog.\tПес.\tnope\tA1\n", encoding="utf-8")
            loaded = words.load_words(path)
            self.assertEqual([(w.en, w.uk) for w in loaded], [("cat", "кіт")])

    def test_finish_lesson_gives_xp_once_a_day(self):
        t = progress.Tracker(progress.Progress(), autosave=False)
        first = t.finish_lesson(self.today)
        self.assertEqual(first.xp, progress.XP["lesson"])
        self.assertIn("lesson_1", [a.id for a in first.unlocked])
        self.assertEqual(t.finish_lesson(self.today).xp, 0)


class WordlistTest(unittest.TestCase):
    """Перевірка самого словника: формат, рівні, теми, без повторів."""

    def test_wordlist_is_clean(self):
        lines = words.WORDLIST.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(words.WORDS), "у словнику є биті рядки або повтори")
        for w in words.WORDS:
            self.assertRegex(w.uk, "[а-яіїєґА-ЯІЇЄҐ]", w.en)
            self.assertRegex(w.example_uk, "[а-яіїєґА-ЯІЇЄҐ]", w.en)
            self.assertNotRegex(w.uk + w.example_uk, "[ыэъё]", f"{w.en}: російські літери")
        levels = [words.LEVELS.index(w.level) for w in words.WORDS]
        self.assertEqual(levels, sorted(levels), "слова мають іти від A1 до B1")


if __name__ == "__main__":
    unittest.main()
