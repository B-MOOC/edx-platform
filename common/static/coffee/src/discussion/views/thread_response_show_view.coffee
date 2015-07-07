if Backbone?
  class @ThreadResponseShowView extends DiscussionContentShowView
    initialize: ->
        super()
        @listenTo(@model, "change", @render)

    renderTemplate: ->
        @template = _.template($("#thread-response-show-template").html())
        context = _.extend(
            {
                cid: @model.cid,
                author_display: @getAuthorDisplay(),
                endorser_display: @getEndorserDisplay()
            },
            @model.attributes
        )
        @template(context)

    render: ->
      @$el.html(@renderTemplate())
      @delegateEvents()
      @renderAttrs()
      @$el.find(".posted-details .timeago").timeago()
      @convertMath()
      @

    convertMath: ->
      element = @$(".response-body")
      element.html DiscussionUtil.postMathJaxProcessor DiscussionUtil.markdownWithHighlight element.text()
<<<<<<< HEAD
      if MathJax?
        MathJax.Hub.Queue ["Typeset", MathJax.Hub, element[0]]
=======
      MathJax.Hub.Queue ["Typeset", MathJax.Hub, element[0]]

    markAsStaff: ->
      if DiscussionUtil.isStaff(@model.get("user_id"))
        @$el.addClass("staff")
        @$el.prepend('<div class="staff-banner">' + gettext('staff') + '</div>')
      else if DiscussionUtil.isTA(@model.get("user_id"))
        @$el.addClass("community-ta")
        @$el.prepend('<div class="community-ta-banner">E-tutor</div>')
>>>>>>> fa0bd35cc1c2ef00890f1bba3b8be2eeb72422b4

    edit: (event) ->
        @trigger "response:edit", event

    _delete: (event) ->
        @trigger "response:_delete", event
