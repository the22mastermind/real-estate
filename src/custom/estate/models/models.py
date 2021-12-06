# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, ValidationError


class EstateProperty(models.Model):
  _name = 'estate.property'
  _description = 'Estate Properties'
  _order = 'id desc'

  name = fields.Char(required=True)
  description = fields.Text()
  postcode = fields.Char()
  date_availability = fields.Date(copy=False, default=date.today() + relativedelta(months=3))
  expected_price = fields.Float(required=True)
  selling_price = fields.Float(readonly=True, copy=False)
  bedrooms = fields.Integer(default=2)
  living_area = fields.Integer()
  facades = fields.Integer()
  garage = fields.Boolean()
  garden = fields.Boolean()
  garden_area = fields.Integer()
  garden_orientation = fields.Selection(
    string='Orientation',
    selection=[('north', 'North'), ('south', 'South'), ('east', 'East'), ('west', 'West')],
    help='Garden orientation'
  )
  active = fields.Boolean(default=True)
  state = fields.Selection(
    selection=[('new', 'New'), ('offer received', 'Offer Received'), ('offer accepted', 'Offer Accepted'), ('sold', 'Sold'), ('canceled', 'Canceled')],
    default='new',
    copy=False,
    required=True
  )
  property_type_id = fields.Many2one('estate.property.type', string='Property Type')
  tag_ids = fields.Many2many('estate.property.tag', string='Tags')
  buyer = fields.Many2one('res.partner', copy=False)
  salesperson = fields.Many2one('res.users', default=lambda self: self.env.user)
  offer_ids = fields.One2many('estate.property.offer', 'property_id', string='Offers')
  total_area = fields.Float(compute='_compute_total_area')
  best_price = fields.Float(compute='_compute_best_offer')

  _sql_constraints = [
    ('check_expected_price', 'CHECK(expected_price >= 0)', 'The expected price must be strictly positive'),
    ('check_selling_price', 'CHECK(selling_price >= 0)', 'The selling price must be strictly positive'),
  ]

  @api.depends('living_area', 'garden_area')
  def _compute_total_area(self):
    for record in self:
      record.total_area = record.living_area + record.garden_area

  @api.depends('offer_ids')
  def _compute_best_offer(self):
    for record in self:
      record.best_price = max(record.offer_ids.mapped('price'), default=0)
  
  @api.onchange('garden')
  def _onchange_garden(self):
    if self.garden:
      self.garden_area = 10
      self.garden_orientation = 'north'
    else:
      self.garden_area = 0
      self.garden_orientation = ''

  @api.onchange('expected_price', 'selling_price')
  @api.constrains('expected_price', 'selling_price')
  def _check_selling_price(self):
    for record in self:
      for offer in record.offer_ids:
        if offer.status == 'accepted' and record.selling_price < (record.expected_price * (0.9)):
          raise ValidationError(f'The selling price cannot be lower than 90% of the expected price')

  def action_set_status_sold(self):
    for record in self:
      if record.state == 'canceled':
        raise UserError('Canceled properties cannot be sold!')
      elif record.state == 'sold':
        raise UserError('The property is already sold!')
      else:
        record.state = 'sold'
      return True

  def action_set_status_canceled(self):
    for record in self:
      if record.state == 'sold':
        raise UserError('Sold properties cannot be canceled!')
      elif record.state == 'canceled':
        raise UserError('The property is already canceled!')
      else:
        record.state = 'canceled'
      return True


class EstatePropertyType(models.Model):
  _name = 'estate.property.type'
  _description = 'Estate Property Types'
  _order = 'sequence, name'

  name = fields.Char(required=True)
  property_ids = fields.One2many('estate.property', 'property_type_id', string='Properties')
  sequence = fields.Integer('Sequence', default=1, help='Used to order property types')

  _sql_constraints = [
    ('name_unique', 'unique(name)', 'The property type must be unique')
  ]


class EstatePropertyTag(models.Model):
  _name = 'estate.property.tag'
  _description = 'Estate Property Tags'
  _order = 'name'

  name = fields.Char(required=True)
  color = fields.Integer()

  _sql_constraints = [
    ('name_unique', 'unique(name)', 'The tag name must be unique')
  ]


class EstatePropertyOffer(models.Model):
  _name = 'estate.property.offer'
  _description = 'Estate Property Offer'
  _order = 'price desc'

  price = fields.Float()
  status = fields.Selection(
    selection=[('accepted', 'Accepted'), ('refused', 'Refused')],
    copy=False
  )
  partner_id = fields.Many2one('res.partner', required=True)
  property_id = fields.Many2one('estate.property', required=True)
  validity = fields.Integer(default=7)
  date_deadline = fields.Date(compute='_compute_deadline', inverse='_inverse_deadline')

  _sql_constraints = [
    ('check_price', 'CHECK(price > 0)', 'The offer price must be strictly positive')
  ]

  @api.depends('create_date', 'validity')
  def _compute_deadline(self):
    for record in self:
      if record.create_date:
        record.date_deadline = record.create_date + relativedelta(days=record.validity)
      else:
        record.date_deadline = date.today() + relativedelta(days=record.validity)

  def _inverse_deadline(self):
    for record in self:
      new_deadline = datetime.strptime(record.date_deadline.strftime('%Y-%m-%d'), '%Y-%m-%d')
      new_create_date = datetime.strptime(record.create_date.strftime('%Y-%m-%d'), '%Y-%m-%d')
      record.validity = abs((new_deadline - new_create_date).days)

  def action_accept_offer(self):
    for record in self:
      record.status = 'accepted'
      record.property_id.buyer = record.partner_id
      record.property_id.selling_price = record.price
      record.property_id.state = 'offer accepted'
      for offer in record.property_id.offer_ids:
        if not offer.id == record.id:
          offer.status = 'refused'
      return True

  def action_refuse_offer(self):
    for record in self:
      record.status = 'refused'
      record.property_id.buyer = None
      record.property_id.selling_price = 0
      for offer in record.property_id.offer_ids:
        if not offer.id == record.id:
          offer.status = 'accepted'
      return True
