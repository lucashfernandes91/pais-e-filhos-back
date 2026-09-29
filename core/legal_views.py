from django.shortcuts import render


def privacy_policy(request):
    return render(request, 'legal/privacy.html')


def terms_of_use(request):
    return render(request, 'legal/terms.html')
