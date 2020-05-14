import yaml

with open(r'jiselConf.yaml') as file:
    # The FullLoader parameter handles the conversion from YAML
    # scalar values to Python the dictionary format
    jiselConf = yaml.load(file, Loader=yaml.FullLoader)

    print(jiselConf)


def detect_text_uri(uri):
    """Detects text in the file."""
    from google.cloud import vision
    import io
    # client = vision.ImageAnnotatorClient()
    client = vision.ImageAnnotatorClient.from_service_account_json(jiselConf['goog'])


    image = vision.types.Image()
    image.source.image_uri = uri
    response = client.text_detection(image=image)
    texts = response.text_annotations
    # print('"{}"'.format(texts[0].description))
    # for text in texts:
    #     print('"{}"'.format(text.description))
    #
    #     vertices = (['({},{})'.format(vertex.x, vertex.y)
    #                 for vertex in text.bounding_poly.vertices])
    #     #
    #     print('bounds: {}'.format(','.join(vertices)))

    return texts and texts[0].description or 'Out of Range'

if __name__ == "__main__":
    detect_text_uri('https://gyazo.com/434fa589183c8e222f715e2c6fd2bd83.jpg')
    # detect_text_uri('https://i.gyazo.com/653549240726a9ccdf867aeaf0bed44c.jpg')


