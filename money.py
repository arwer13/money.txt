from collections import defaultdict
import re
import os
import datetime
import bisect
from functools import total_ordering
from dateutil import rrule
from dateutil.relativedelta import relativedelta

@total_ordering
class Entry:

    def __init__(self, s=None, date=None):
        self.cats = []
        self.tags = []
        self.day = None
        self.value = 0
        self.note = ""
        self.cmd = None
        if s is None:
            return
        if s.strip() == "":
            return
        elif s.strip()[0] == '#':
            return
        cmd_re = re.compile(r'\s*(\d\d\d\d\.\d\d\.\d\d)?\s+!(.*?) +([\(\)\d\+-\.\*,]+)\s*')
        entry_re = re.compile(r' *(\d\d\d\d\.\d\d\.\d\d)? *(.*?) +([\(\)\d\+-\.,\*]+)\w*(.*)')

        cmd_match = cmd_re.match(s)
        if cmd_match is not None:
            date_str, self.cmd, value_str = cmd_match.groups()
            self.day = datetime.date(*map(int, date_str.split('.')))
            self.value = eval(value_str)
        else:
            try:
                date_gr, desc_gr, value_gr, note_gr = entry_re.match(s).groups()
            except AttributeError as e:
                msg = str(e)
                print("Error line: {} ({})".format(s, e))
                return

            value_gr = value_gr.replace(',', '.')
            note_words = list(filter(None, note_gr.split()))
            self.day = date if date_gr is None else datetime.date(*map(int, date_gr.split('.')))
            self.cats = tuple(filter(None, map(str.strip, desc_gr.split(','))))
            self.value = eval(value_gr) if value_gr[0] == '+' else -eval(value_gr)
            self.note = ' '.join(filter(lambda x: x[0] != '#', note_words))
            self.tags = list(map(lambda x: x[1:], filter(lambda x: x[0] == '#', note_words)))

    def __str__(self):
        if self.cmd is None:
            value_str = "{:.1f}".format(-self.value) if self.value < 0 else "+{:.0f}".format(self.value)
            return "{} {} {} {} {}".format(self.day, ','.join(self.cats), value_str,
                                           '' if self.note is None else self.note, ' '.join(map(lambda x: '#'+x, self.tags)))
        else:
            return "{} !{} {:.1f}".format(self.day, self.cmd, self.value)

    def __repr__(self):
        return '\n'+str(self.__dict__)

    def __eq__(self, other):
        return self.cats == other.cats and self.day == other.day and self.tags == other.tags \
               and self.value == other.value and self.note == other.note

    def __gt__(self, other):
        return self.day > other.day


class Bookkeeper:

    def __init__(self, month_start_day, weekly_categories):
        self.entries = []
        self.last_day = None
        self.month_start_day = month_start_day
        self.weekly_categories = weekly_categories

    def closest_monday(self, date):
        date -= datetime.timedelta(days=date.weekday())
        return date

    # scary way to step back to known date
    def closest_month_beginning(self, date):
        while date.day != self.month_start_day:
            date -= datetime.timedelta(days=1)
        return date

    def filter(self, period=None, cats=None, tags=None, sign=None, cmds=(None,)):
        result = self.entries
        result = list(filter(lambda x: x.cmd in cmds, result))

        if sign == "+":
            result = filter(lambda a: a.value > 0, result)
        elif sign == "-":
            result = filter(lambda a: a.value < 0, result)

        if period is not None:
            pr = [None, None]
            pr[0] = period[0] if period[0] is not None else self.entries[0].day
            pr[1] = period[1] if period[1] is not None else datetime.date.today()
            result = filter(lambda x: pr[0] <= x.day <= pr[1], result)

        if cats is not None:
            filtered_by_cats = list()
            for e in result:
                for c in cats:
                    if len(e.cats) >= len(c) and all([e.cats[i] == c[i] for i in range(len(c))]):
                        filtered_by_cats.append(e)
                        continue
            result = filtered_by_cats

        if tags is not None:
            result = filter(lambda x: x.tags.intersection(tags) != set(), result)

        return result

    def account(self, line):
        if line == "":
            return
        e = Entry(line, self.last_day)
        self.last_day = e.day
        if e != Entry():
            if len(self.entries) > 0 and self.entries[-1].day >= e.day:
                self.entries.append(e)
            else:
                bisect.insort_right(self.entries, e)

    def get_total_value(self):
        # milestone = self.milestones[-1]
        # return milestone[2] + sum([e.value for e in self.filter(period=(milestone[0], datetime.date.today()))])
        result = 0.0
        for e in self.entries:
            if e.cmd == "milestone":
                result = e.value
            else:
                result += e.value
        return result

    def every_calendar_weak(self):
        result = dict()
        start_date = self.closest_monday(min(e.day for e in self.entries))
        for dt in rrule.rrule(rrule.WEEKLY, dtstart=start_date, until=datetime.date.today()):
            period = dt.date(), dt.date() + datetime.timedelta(days=6)
            week_expenses = self.filter(period=period, sign="-", cats=self.weekly_categories)
            week_expenses = list(week_expenses)
            notes = [str(x) for x in week_expenses]
            value = -sum(map(lambda x: x.value, week_expenses))
            result[period] = {"value": value, "note": notes}
        return result

    def expenses_by_top_categories(self, entries=None):
        if entries is None:
            entries = self.entries
        result = defaultdict(lambda : {"value": 0.0, "note": []})
        for x in filter(lambda x: x.value < 0, entries):
            cat = x.cats[:1]
            result[cat]["value"] += -x.value
            result[cat]["note"].append(str(x))
        return result

    def monthly_by_categories(self):
        start_date = self.closest_month_beginning(min(e.day for e in self.entries))
        result = defaultdict(list)
        for dt in rrule.rrule(rrule.MONTHLY, dtstart=start_date, until=datetime.date.today()):
            period = dt.date(), dt.date() + relativedelta(months=1) - relativedelta(days=1)
            result[period] = self.filter(period=period)
        result = {k: self.expenses_by_top_categories(v) for k, v in result.items()}
        return result

    def all_categories(self):
        result = set()
        for et in self.entries:
            result.add(et.cats)
        return result


model_template = {
    "title": None,
    "total_value": None,
    "current_date": None,
    "monthly_by_categories": None
}


def make_model(bk, weekly_categories):
    result = dict()
    result["total_value"] = bk.get_total_value()

    expenses_weekly = bk.every_calendar_weak()
    expenses_array = [[], []]
    for i, period in enumerate(sorted(expenses_weekly.keys())):
        begin = period[0].strftime("%d.%m")
        end = period[1].strftime("%d.%m")
        # end = (period[1] - datetime.timedelta(days=1)).strftime("%d.%m")
        expenses_array[0].append("{}-{}".format(begin, end))
        expenses_array[1].append(expenses_weekly[period])
    result["selected_expenses_weekly"] = expenses_array
    result["weekly_categories"] = ", ".join([x[0] for x in weekly_categories])

    monthly_by_categories = bk.monthly_by_categories()
    all_categories = list({c for mv in monthly_by_categories.values() for c in mv})
    all_categories = sorted(all_categories,
                            key=lambda cc: sum([mm[cc]["value"] for mm in monthly_by_categories.values()]), reverse=True)
    array = [["Month", "Income", "Total spent", "Balance"] + [c[0] for c in all_categories]]
    for m in sorted(monthly_by_categories.keys()):
        mv = monthly_by_categories[m]
        month = "{} {} ({}-{})".format(m[0].strftime("%Y"), m[0].strftime("%B"), m[0].strftime("%d.%m"), m[1].strftime("%d.%m"))
        total_spent = sum([x["value"] for x in mv.values()])
        income = {"value": 0, "note": []}
        for x in bk.filter(period=m, sign="+"):
            income["value"] += x.value
            income["note"].append(str(x))
        balance = income["value"] - total_spent
        row = [month, income, total_spent, balance]
        for c in all_categories:
            row.append(mv.get(c, 0))
        array.append(row)
    result["monthly_by_categories"] = array

    errors_arr = [[], []]
    current_value = 0.0
    left_date = bk.entries[0].day
    for e in bk.filter(cmds=(None, "milestone")):
        if e.cmd == "milestone":
            period = "{}-{}".format(left_date.strftime("%d.%m"), e.day.strftime("%d.%m"))
            errors_arr[0].append(period)
            cell = {
                "value":  e.value - current_value,
                "note": ["Accounted: {:.0f}".format(current_value), "Actual: {:.0f}".format(e.value)]
            }
            errors_arr[1].append(cell)
            current_value = e.value
            left_date = e.day
        else:
            current_value += e.value

    result["errors"] = errors_arr

    return result


class LineFormatError(Exception):
    pass


def load_data(config):
    MONEY_TXT_PATH_ENV = "MONEY_TXT_PATH"
    DROPBOX_TOKEN_ENV = "MONEY_TXT_DROPBOX_TOKEN"

    if MONEY_TXT_PATH_ENV in os.environ:
        print('Loading local money.txt from {}'.format(MONEY_TXT_PATH_ENV))
        with open(os.environ[MONEY_TXT_PATH_ENV]) as ff:
            text = ff.read()
    elif DROPBOX_TOKEN_ENV in os.environ:
        print('Loading local money.txt from Dropbox')
        import dropbox_stuff
        text = dropbox_stuff.get_money_txt(os.environ[DROPBOX_TOKEN_ENV])
        if text is None:
            print('Can not load money.txt from Dropbox')
    else:
        raise RuntimeError("Can not find any of environmental variables: {}".format(
            ', '.join([MONEY_TXT_PATH_ENV, DROPBOX_TOKEN_ENV])))

    start_index = text.find("START")
    start_index = text.find("\n", start_index)
    if start_index != -1:
        text = text[start_index:]
    bk = Bookkeeper(config.month_period_day, config.weekly_categories)
    for line in text.split("\n"):
        try:
            bk.account(line)
        except Exception as e:
            raise LineFormatError('Error\n{}\nprocessing line\n{}'.format(e, line))

    return bk