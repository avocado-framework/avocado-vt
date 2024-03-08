from ...managers.image import _backing_mgr_dispatcher


def handle_image(config):
    """
    :param backing_id: The resource backing id
    :type backing_id: string
    :param config: The specified action and the snippet of
                   the resource's spec and meta info used for update
    :type config: dict
    """
    image_handler = _image_handler_dispatcher.dispatch(config)
    image_handler.do(config)
