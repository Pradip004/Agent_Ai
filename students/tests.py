from io import BytesIO
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from .ai_helper import AIServiceError, ask_openai
from .models import Candidate, Student


class OpenAIServiceTests(SimpleTestCase):
    @override_settings(OPENAI_API_KEY="test-key", OPENAI_MODEL="gpt-4o-mini", OPENAI_TIMEOUT=60)
    @patch("students.ai_helper.requests.post")
    def test_sends_conversation_to_openai(self, post):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
        }
        post.return_value = response

        answer = ask_openai([{"role": "user", "content": "Hi"}])

        self.assertEqual(answer, "Hello!")
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "gpt-4o-mini")
        self.assertEqual(post.call_args.kwargs["json"]["messages"][-1], {
            "role": "user", "content": "Hi",
        })

    @override_settings(OPENAI_API_KEY="")
    def test_requires_an_openai_api_key(self):
        with self.assertRaisesMessage(AIServiceError, "OPENAI_API_KEY"):
            ask_openai([{"role": "user", "content": "Hi"}])


class OpenAIChatViewTests(TestCase):
    def test_chat_page_is_public_and_login_routes_are_unavailable(self):
        self.assertEqual(self.client.get(reverse("ask_ai")).status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    @patch("students.views.ai_helper.ask_openai", return_value="Hello from OpenAI.")
    def test_chat_reply_is_shown_in_conversation(self, ask_openai_mock):
        response = self.client.post(reverse("ask_ai"), {"question": "Hello"})

        self.assertRedirects(response, reverse("ask_ai"))
        ask_openai_mock.assert_called_once()
        page = self.client.get(reverse("ask_ai"))
        self.assertContains(page, "Hello from OpenAI.")
        self.assertContains(page, "OpenAI-powered assistant")

    def test_student_and_candidate_record_pages_are_available(self):
        self.assertEqual(self.client.get(reverse("student_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("candidate_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("student_add")).status_code, 200)
        self.assertEqual(self.client.get(reverse("candidate_add")).status_code, 200)

    def test_student_can_be_added_individually(self):
        response = self.client.post(reverse("student_add"), {
            "roll_number": "S-101",
            "full_name": "Asha Patel",
            "department": "Science",
            "email": "asha@example.com",
            "phone": "1234567890",
            "class_name": "10A",
            "marks": "88.50",
            "attendance": "95.00",
            "fees_paid": "on",
        })

        self.assertRedirects(response, reverse("student_list"))
        self.assertTrue(Student.objects.filter(roll_number="S-101").exists())

    def test_student_csv_import_skips_existing_roll_numbers(self):
        Student.objects.create(
            roll_number="S-101", full_name="Existing Student", department="Science",
        )
        upload = SimpleUploadedFile(
            "students.csv",
            b"roll_number,full_name,department\nS-101,Changed Name,Arts\nS-102,New Student,Arts\n",
            content_type="text/csv",
        )

        response = self.client.post(reverse("student_import"), {"file": upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 created; 1 skipped")
        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(Student.objects.get(roll_number="S-101").full_name, "Existing Student")

    def test_student_xlsx_import(self):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["roll_number", "full_name", "department"])
        worksheet.append(["S-103", "Noah Singh", "Commerce"])
        content = BytesIO()
        workbook.save(content)
        upload = SimpleUploadedFile(
            "students.xlsx",
            content.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(reverse("student_import"), {"file": upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 created; 0 skipped")
        self.assertTrue(Student.objects.filter(roll_number="S-103").exists())

    def test_candidate_can_be_added_individually(self):
        response = self.client.post(reverse("candidate_add"), {
            "full_name": "Ravi Kumar",
            "position": "Engineer",
            "years_experience": "3.5",
            "status": Candidate.ApplicationStatus.NEW,
        })

        self.assertRedirects(response, reverse("candidate_list"))
        self.assertTrue(Candidate.objects.filter(full_name="Ravi Kumar").exists())

    def test_candidate_csv_import(self):
        upload = SimpleUploadedFile(
            "candidates.csv",
            b"full_name,position,email,years_experience\n"
            b"Mina Shah,Designer,mina@example.com,2\n"
            b"Mina Shah,Designer,mina@example.com,4\n",
            content_type="text/csv",
        )

        response = self.client.post(reverse("candidate_import"), {"file": upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 created; 1 skipped")
        self.assertTrue(Candidate.objects.filter(email="mina@example.com").exists())
        self.assertEqual(Candidate.objects.get(email="mina@example.com").years_experience, 2)
