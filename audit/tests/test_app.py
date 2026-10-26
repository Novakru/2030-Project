"""Exercise UI state and real DB writes with Streamlit's built-in AppTest."""
import json
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest
from audit import db
from audit.import_json_to_db import import_documents
from audit.tests.test_backend import positive, negative

APP = Path(__file__).resolve().parents[1] / "app.py"


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "reviews.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def start(self):
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertFalse(app.exception)
        return app

    def open_app(self):
        import_documents(self.database, [("fixtures.json", json.dumps([positive(), negative()]))])
        app = self.start()
        app.text_input(key="database_path").set_value(str(self.database))
        app.button(key="open_db").click().run()
        self.assertFalse(app.exception)
        return app

    def button(self, app, label):
        return next(b for b in app.button if b.label == label)

    def test_open_review_accept_undo_and_reject(self):
        app = self.open_app()
        self.assertEqual(app.session_state["current_record"], "neg_fixture")
        self.assertTrue(self.button(app, "通过并下一条").disabled)
        app.text_input(key="reviewer").set_value("UI reviewer").run()
        comment = next(t for t in app.text_input if t.label == "审核意见（可选）")
        comment.set_value("A1 label confirmed")
        self.button(app, "通过并下一条").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(db.get_record(self.database, "neg_fixture")["status"], "accepted")
        self.assertEqual(app.session_state["current_record"], "pos_fixture")
        app.button(key="nav_prev").click().run()
        self.assertEqual(app.session_state["current_record"], "neg_fixture")
        self.assertFalse(any(b.label == "通过并下一条" for b in app.button))
        self.button(app, "撤销审核").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(db.get_record(self.database, "neg_fixture")["status"], "pending")
        self.button(app, "拒绝并下一条").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(db.get_record(self.database, "neg_fixture")["status"], "rejected")
        self.assertEqual(len(db.review_history(self.database, "neg_fixture")), 3)
        self.assertEqual(app.session_state["current_record"], "pos_fixture")

    def test_first_import_then_reopen_and_export_filtered(self):
        source = self.root / "source.json"
        source.write_text(json.dumps([positive(), negative()]), encoding="utf-8")
        original = source.read_bytes()
        app = self.start()
        app.radio(key="connection_mode").set_value("首次建库并导入").run()
        app.text_input(key="database_path").set_value(str(self.database))
        app.text_area(key="inputs_initial").set_value(str(source))
        self.button(app, "导入数据库").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["active_db"], str(self.database))
        self.assertEqual(db.statistics(self.database)["total"], 2)
        app.selectbox(key="filter_kind").set_value("negative").run()
        app.radio(key="workspace_page").set_value("导出").run()
        app.text_input(key="export_dir").set_value(str(self.root / "export"))
        self.button(app, "生成时间戳导出").click().run()
        self.assertFalse(app.exception)
        runs = list((self.root / "export").glob("review_*"))
        self.assertEqual(len(runs), 1)
        exported = json.loads((runs[0] / "records.json").read_text(encoding="utf-8"))
        self.assertEqual([r["id"] for r in exported], ["neg_fixture"])
        self.assertEqual(source.read_bytes(), original)
        reopened = self.start()
        reopened.text_input(key="database_path").set_value(str(self.database))
        reopened.button(key="open_db").click().run()
        self.assertFalse(reopened.exception)
        self.assertEqual(db.statistics(self.database)["pending"], 2)

    def test_filters_empty_results_and_missing_database_error(self):
        app = self.open_app()
        app.selectbox(key="filter_status").set_value("accepted").run()
        self.assertFalse(app.exception)
        self.assertTrue(any("没有记录" in item.value for item in app.info))
        app.text_input(key="database_path").set_value(str(self.root / "missing.sqlite3"))
        app.button(key="open_db").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertFalse((self.root / "missing.sqlite3").exists())

    def test_page_navigation_and_refresh_do_not_submit_reviews(self):
        app = self.open_app()
        self.assertTrue(app.button(key="nav_prev").disabled)
        self.assertFalse(app.button(key="nav_next").disabled)
        app.button(key="nav_next").click().run()
        self.assertEqual(app.session_state["current_record"], "pos_fixture")
        self.assertTrue(app.button(key="nav_next").disabled)
        app.button(key="nav_prev").click().run()
        self.assertEqual(app.session_state["current_record"], "neg_fixture")
        self.assertEqual(db.statistics(self.database)["pending"], 2)
        self.assertFalse(db.review_history(self.database, "neg_fixture"))
        app.text_input(key="reviewer").set_value("Reviewer").run()
        self.button(app, "通过并下一条").click().run()
        self.assertEqual(len(app.session_state["review_queue"]), 2)
        app.button(key="refresh_queue").click().run()
        self.assertEqual(app.session_state["review_queue"], ["pos_fixture"])

    def test_filter_reset_and_last_record_decision(self):
        app = self.open_app()
        app.button(key="nav_next").click().run()
        app.selectbox(key="filter_kind").set_value("negative").run()
        self.assertEqual(app.session_state["queue_index"], 0)
        self.assertEqual(app.session_state["review_queue"], ["neg_fixture"])
        app.text_input(key="reviewer").set_value("Reviewer").run()
        self.button(app, "拒绝并下一条").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["current_record"], "neg_fixture")
        self.assertTrue(self.button(app, "撤销审核"))
        self.assertTrue(app.button(key="nav_next").disabled)


if __name__ == "__main__":
    unittest.main()
