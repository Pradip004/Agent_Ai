from django.urls import path

from . import views

urlpatterns = [
    path("ask-ai/", views.ask_ai, name="ask_ai"),
    path("export/<str:fmt>/", views.export_report, name="export_report"),
    path("", views.ask_ai, name="home"),
    path("students/", views.dashboard, name="dashboard"),
    path("students/add/", views.student_add, name="student_add"),
    path("students/<int:pk>/edit/", views.student_edit, name="student_edit"),
    path("students/<int:pk>/delete/", views.student_delete, name="student_delete"),
    path("candidates/", views.candidate_list, name="candidate_list"),
    path("candidates/add/", views.candidate_add, name="candidate_add"),
    path("candidates/<int:pk>/edit/", views.candidate_edit, name="candidate_edit"),
    path("candidates/<int:pk>/delete/", views.candidate_delete, name="candidate_delete"),
    path("candidates/<int:pk>/resume/", views.candidate_resume, name="candidate_resume"),
    path("import/", views.student_add, name="import_excel"),
]