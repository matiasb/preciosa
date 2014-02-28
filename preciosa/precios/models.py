# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.db.models import Min
from model_utils import Choices
from model_utils.fields import MonitorField
from model_utils.models import TimeStampedModel
from easy_thumbnails.fields import ThumbnailerImageField
from image_cropping import ImageRatioField, ImageCropField
from treebeard.mp_tree import MP_Node
from tools.utils import one


class Categoria(MP_Node):
    nombre = models.CharField(max_length=100)
    node_order_by = ['nombre']

    def reload(self):
        if self.id:
            return Categoria.objects.get(pk=self.id)
        return self

    def __unicode__(self):
        if not self.is_root():
            return unicode(self.get_parent()) + " > " + self.nombre
        return self.nombre

    class Meta:
        verbose_name = u"categoria"
        verbose_name_plural = u"categorias"

    @models.permalink
    def get_absolute_url(self):
        return ('lista_productos', (self.id, slugify(self.nombre)), {})

    @classmethod
    def por_clasificar(cls):
        return cls.objects.get(nombre='A CLASIFICAR').get_children()


class Producto(models.Model):
    UM_GRAMO = 'gr'
    UM_KILO = 'kg'
    UM_ML = 'ml'
    UM_L = 'l'
    UM_UN = 'unidad'
    UM_SM = 'SM'
    UM_MR = 'MR'

    UM_TRANS = {u'LT': 'l', u'UN': 'unidad'}

    UNIDADES_PESO = [UM_GRAMO, UM_KILO]
    UNIDADES_VOLUMEN = [UM_ML, UM_L]
    UNIDADES_CHOICES = Choices(UM_GRAMO, UM_KILO, UM_ML, UM_L,
                               UM_UN, UM_SM, UM_MR)

    descripcion = models.CharField(max_length=250)
    upc = models.CharField(verbose_name=u"Código de barras",
                           max_length=13, unique=True, null=True, blank=True)
    categoria = models.ForeignKey('Categoria')
    marca = models.ForeignKey('Marca', null=True, blank=True)
    contenido = models.DecimalField(max_digits=5, decimal_places=1,
                                    null=True, blank=True)
    unidad_medida = models.CharField(max_length=10,
                                     choices=UNIDADES_CHOICES, null=True, blank=True)
    notas = models.TextField(null=True, blank=True)
    foto = ThumbnailerImageField(null=True, blank=True, upload_to='productos')
    acuerdos = models.ManyToManyField('Cadena', through='PrecioEnAcuerdo')

    def __unicode__(self):
        return self.descripcion

    class Meta:
        verbose_name = u"producto"
        verbose_name_plural = u"productos"

    @models.permalink
    def get_absolute_url(self):
        return ('detalle_producto',
                (self.categoria.id, slugify(self.categoria.nombre),
                 self.id, slugify(self.descripcion)), {})

    def mejor_precio(self):
        last_month = datetime.today() - timedelta(days=30)
        best = self.precio_set.filter(created__gte=last_month).aggregate(Min('precio'))
        return best['precio__min']


class Marca(models.Model):
    """
    Es el marca comercial de un producto.
    Ejemplo: Rosamonte
    """
    fabricante = models.ForeignKey('EmpresaFabricante', null=True, blank=True)
    nombre = models.CharField(max_length=100, unique=True,
                              verbose_name=u"Nombre de la marca")
    logo = ImageCropField(null=True, blank=True,
                          upload_to='marcas')

    # size is "width x height"
    logo_cropped = ImageRatioField('logo', '150x125',
                                   verbose_name=u'Recortar logo', free_crop=True)
    logo_changed = MonitorField(monitor='logo', editable=False)

    def __unicode__(self):
        return self.nombre

    class Meta:
        unique_together = (('nombre', 'fabricante'))
        verbose_name = u"marca"
        verbose_name_plural = u"marcas"


class AbstractEmpresa(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    logo = ImageCropField(null=True, blank=True,
                          upload_to='empresas')
    logo_cropped = ImageRatioField('logo', '150x125',
                                   verbose_name=u'Recortar logo', free_crop=True)
    logo_changed = MonitorField(monitor='logo', editable=False)

    def __unicode__(self):
        return self.nombre

    class Meta:
        abstract = True


class Cadena(AbstractEmpresa):
    """Cadena de supermercados. Por ejemplo Walmart"""

    cadena_madre = models.ForeignKey('self', null=True, blank=True,
                                     help_text="Jumbo y Vea son de Cencosud")

    class Meta:
        verbose_name = u"cadena de supermercados"
        verbose_name_plural = u"cadenas de supermercados"


class EmpresaFabricante(AbstractEmpresa):
    pass


class Sucursal(models.Model):
    objects = models.GeoManager()

    nombre = models.CharField(max_length=100, null=True, blank=True,
                              help_text="Denominación común. Ej: Jumbo de Alberdi")
    # direccion sólo puede ser nulo para sucursales online
    direccion = models.CharField(max_length=200, null=True, blank=True)
    ciudad = models.ForeignKey('cities_light.City')
    cp = models.CharField(max_length=100, null=True, blank=True)
    telefono = models.CharField(max_length=100, null=True, blank=True)
    horarios = models.TextField(null=True, blank=True)
    cadena = models.ForeignKey('Cadena', related_name='sucursales',
                               null=True, blank=True,
                               help_text='Dejar en blanco si es un comercio único')

    ubicacion = models.PointField(srid=4326, null=True, blank=True,)
    online = models.BooleanField(default=False,
                                 help_text='Es una sucursal online, no física')
    url = models.URLField(max_length=200, null=True, blank=True)

    def _latitud(self):
        if self.ubicacion:
            return self.ubicacion.y
        return None

    def _longitud(self):
        if self.ubicacion:
            return self.ubicacion.x
        return None

    lat = property(_latitud)
    lon = property(_longitud)

    def clean(self):
        if not one((self.cadena, self.nombre)):
            raise ValidationError(u'Indique la cadena o el nombre del comercio')
        if not one((self.direccion, self.online)):
            raise ValidationError(u'La sucursal debe ser online '
                                  u'o tener direccion física, pero no ambas')
        if self.online and not self.url:
            raise ValidationError(u'La url es obligatoria para sucursales online')

    def __unicode__(self):
        return u"%s (%s)" % (self.nombre or self.cadena, self.direccion or self.url)

    class Meta:
        unique_together = (('direccion', 'ciudad'))
        verbose_name = u"sucursal"
        verbose_name_plural = u"sucursales"


class PrecioManager(models.Manager):

    def historico(self, producto, sucursal, dias=None, distintos=True):
        """
        dado un producto y sucursal
        devuelve una lista de precios y la fecha de su registro
        ordenados de la mas nueva a las más vieja.

        por defecto solo muestra precios distintos.
        Para un historial completo (ejemplo, para graficar
        una curva de evolucion de precio), asigar ``distintos=False``

        dias filtra a registros mas nuevos a los X dias.
        """
        qs = super(PrecioManager, self).get_queryset()
        qs = qs.filter(producto=producto, sucursal=sucursal)
        if dias:
            desde = timezone.now() - timedelta(days=dias)
            qs = qs.filter(created__gte=desde)
        # se ordenará de más nuevo a más viejo, pero
        if distintos:
            qs = qs.distinct('precio')
        qs = qs.values('created', 'precio')
        return sorted(qs, key=lambda i: i['created'], reverse=True)


    def mas_probable(self, producto, sucursal, dias=None, ciudad=None, radio=None):
        """
        Cuando no hay datos especificos de un
        producto para una sucursal (:meth:`historico`),
        debe ofrecerse un precio más probable. Se calcula

         - Precio con más coincidencias para el producto en otras sucursales de la misma cadena en la ciudad (o un radio de distancia)
         - En su defecto, precio online de la cadena
        """
        qs = self.historico(producto, sucursal, dias)
        if len(qs) > 0:
            return qs






class Precio(TimeStampedModel):
    objects = PrecioManager()

    producto = models.ForeignKey('Producto')
    sucursal = models.ForeignKey('Sucursal')
    precio = models.DecimalField(max_digits=8, decimal_places=2)
    usuario = models.ForeignKey(User, null=True, blank=True)

    def __unicode__(self):
        return u'%s: $ %s' % (self.producto, self.precio)

    class Meta:
        verbose_name = u"precio"
        verbose_name_plural = u"precios"




class PrecioEnAcuerdo(models.Model):
    producto = models.ForeignKey('Producto')
    cadena = models.ForeignKey('Cadena',
                               limit_choices_to={'cadena_madre__isnull': True})

    precio_norte = models.DecimalField(max_digits=5, decimal_places=2)
    precio_sur = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = u"precio en acuerdo"
        verbose_name_plural = u"precios en acuerdo"
