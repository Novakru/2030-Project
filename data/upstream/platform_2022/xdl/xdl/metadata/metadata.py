from typing import Optional
from ..steps.templates.metadata import AbstractMetadata

class Metadata(AbstractMetadata):
    """Metadata associated with procedure.

    Args:
        description (str): Brief description of the synthesis.
        publication (str): Publication synthesis was taken from.
        smarts (str): SMARTS string of the transformation.
        product (str): Name of product.
        product_inchi (str): INCHI string of product.
        product_cas (int): CAS number of the product.
        product_vessel (str): Vessel that the product ends up in.
        reaction_class (str): Type of reaction being carried out. At the moment
            not limiting this to specific options, as reaction classification
            can be ambiguous.
    """

    PROP_TYPES = {
        'description': str,
        'product_inchi': str,
        'product_vessel': str,
        'product': str,
        'product_cas': int,
        'smarts': str,
        'publication': str,
        'reaction_class': str,
    }

    DEFAULT_PROPS = {
        'description': None,
        'product_inchi': None,
        'product_vessel': None,
        'product': None,
        'product_cas': None,
        'smarts': None,
        'publication': None,
        'reaction_class': None,
    }

    def __init__(
        self,
        description: Optional[str] = None,
        product_inchi: Optional[str] = None,
        product_vessel: Optional[str] = None,
        product: Optional[str] = None,
        product_cas: Optional[int] = None,
        smarts: Optional[str] = None,
        publication: Optional[str] = None,
        reaction_class: Optional[str] = None,
        **kwargs
    ):
        super().__init__(locals())
