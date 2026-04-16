from django.shortcuts import redirect, render


def settings_view(request):
    from sync2pod.forms import Sync2PodConfigForm
    from sync2pod.models import Sync2PodConfig

    sync2pod_config = Sync2PodConfig.get()
    sync2pod_saved = False

    if request.method == 'POST' and request.POST.get('_app') == 'sync2pod':
        form_sync2pod = Sync2PodConfigForm(request.POST, instance=sync2pod_config)
        if form_sync2pod.is_valid():
            form_sync2pod.save()
            return redirect('/settings/?saved=sync2pod')
    else:
        form_sync2pod = Sync2PodConfigForm(instance=sync2pod_config)

    if request.GET.get('saved') == 'sync2pod':
        sync2pod_saved = True

    # Build kubeconfig context hint using sync2pod's helper
    try:
        from sync2pod.views import _get_kubeconfig_context
        kube_ctx = _get_kubeconfig_context(is_tess=sync2pod_config.is_tess)
    except Exception:
        kube_ctx = None

    return render(request, 'settings.html', {
        'form_sync2pod': form_sync2pod,
        'sync2pod_config': sync2pod_config,
        'sync2pod_saved': sync2pod_saved,
        'kube_ctx': kube_ctx,
        'active_tab': request.GET.get('tab', 'sync2pod'),
    })
