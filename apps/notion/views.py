from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import Http404
import requests
from icecream import ic
from mtools.logger import l_logger

logger = l_logger('notion')

class NotionTest(APIView):

    def get(self, request):
        NotionData = requests.request(
            "GET",
            "https://api.notion.com/v1/pages/e9023dbb30d745bf817f8195532f2967",
            # 前文已介绍过
            headers={
                "Authorization": "secret_jCvRq3TEcw1SxCPxGvWi1dn76vjA6UM164jo2dvRAg0",
                "Notion-Version": "2021-05-13"
            },
        )
        ic(NotionData)
        # return Response(NotionData)
        return Response({
            'ttstus':'test'
        })

