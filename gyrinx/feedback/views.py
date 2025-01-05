from django import forms
from django.shortcuts import render

from gyrinx.feedback.models import Feedback


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ["feedback", "feedback_type"]
        labels = {
            "feedback": "Feedback",
            "feedback_type": "Type",
        }
        help_texts = {
            "feedback": "Please provide as much detail as possible.",
            "feedback_type": "What's this feedback about?",
        }
        widgets = {
            "feedback": forms.Textarea(attrs={"class": "form-control"}),
            "feedback_type": forms.Select(attrs={"class": "form-select"}),
        }


def form(request):
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.user = request.user
            return render(request, "feedback/thanks.html")
    else:
        form = FeedbackForm()

    return render(
        request,
        "feedback/form.html",
        {
            "form": form,
        },
    )
