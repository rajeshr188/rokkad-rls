from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.forms import ProfileUpdateForm


@login_required
def profile_page(request):
	if request.method == "POST":
		form = ProfileUpdateForm(request.POST, instance=request.user)
		if form.is_valid():
			form.save()
			messages.success(request, "Profile updated.")
			return redirect("accounts:profile")
	else:
		form = ProfileUpdateForm(instance=request.user)

	return render(request, "accounts/profile_page.html", {"form": form})
