from django.urls import path

from . import views

urlpatterns = [
    path("", views.ask_ai, name="ask_ai"),
    path("students/", views.student_list, name="student_list"),
    path("students/add/", views.student_add, name="student_add"),
    path("students/import/", views.student_import, name="student_import"),
    path("candidates/", views.candidate_list, name="candidate_list"),
    path("candidates/add/", views.candidate_add, name="candidate_add"),
    path("candidates/import/", views.candidate_import, name="candidate_import"),
]
