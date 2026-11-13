from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


def paginate_queryset(queryset, request, per_page=20):
    """
    Reusable pagination helper used across all list views.

    How Django pagination works:
    1. Paginator splits the queryset into pages of per_page items
    2. We read the page number from the URL query parameter ?page=2
    3. We return only the items for the requested page
    4. The template uses the page object to render navigation buttons

    Returns a page object that contains:
    - page.object_list    → the items for this page
    - page.has_previous() → True if there is a previous page
    - page.has_next()     → True if there is a next page
    - page.previous_page_number() → page number before this one
    - page.next_page_number()     → page number after this one
    - page.number         → current page number
    - paginator.num_pages → total number of pages
    - paginator.count     → total number of records
    """
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get('page', 1)

    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        # If page is not an integer, show first page
        page = paginator.page(1)
    except EmptyPage:
        # If page is out of range, show last page
        page = paginator.page(paginator.num_pages)

    return page, paginator